"""Đóng gói bộ cài offline cho NetOps-Server (DHCP-Server 72, Windows Server 2012 R2 x64):

    python scripts/build_windows_bundle.py [--with-secrets]   → dist/netops/  (chép nguyên thư mục thành C:\\netops)

- Python 3.11.9 embeddable (3.11 còn hỗ trợ Server 2012 R2; 3.12+ không cam kết).
- UCRT app-local: node 72 chưa có KB2999226 → chép bộ DLL downlevel (ucrtbase + api-ms-win-crt-*)
  của Windows 10/11 vào cạnh python.exe (cách triển khai app-local Microsoft cho phép).
- Thư viện cài sẵn bằng `pip --target --platform win_amd64 --python-version 3.11` theo requirements-netops.txt.
- --with-secrets: tạo secrets/credentials.md CHỈ gồm dòng `netops`, `netops FW` và `vManager (33)` từ file credentials
  cục bộ (không có root EVE). Thư mục dist/ bị .gitignore.
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.abspath(os.path.join(HERE, ".."))
DIST = os.path.join(BOT, "dist", "netops")
CACHE = os.path.join(BOT, "dist", "cache")
PY_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
DOWNLEVEL = r"C:\Windows\System32\downlevel"
APP_ITEMS = ["campus", "scripts", "tests", "main.py", "telegram_bot.py", "README.md"]
SECRET_TAGS = ["netops (SSH Site 100)", "netops FW", "vManager (33)"]


def step(msg):
    print(f"== {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-secrets", action="store_true")
    ap.add_argument("--out", help="thư mục đích (nên ở ổ cục bộ; OneDrive ghi hàng nghìn file nhỏ rất chậm)")
    a = ap.parse_args()
    global DIST, CACHE
    if a.out:
        DIST, CACHE = os.path.join(a.out, "netops"), os.path.join(a.out, "cache")
    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(CACHE, exist_ok=True)

    step("Python 3.11.9 embeddable")
    zpath = os.path.join(CACHE, os.path.basename(PY_URL))
    if not os.path.isfile(zpath):
        urllib.request.urlretrieve(PY_URL, zpath)
    pydir = os.path.join(DIST, "python")
    with zipfile.ZipFile(zpath) as z:
        z.extractall(pydir)
    with open(os.path.join(pydir, "python311._pth"), "w", encoding="ascii") as f:
        f.write("python311.zip\n.\n..\\app\n..\\lib\n")

    step("UCRT app-local (downlevel)")
    n = 0
    for name in os.listdir(DOWNLEVEL):
        low = name.lower()
        if low == "ucrtbase.dll" or low.startswith("api-ms-win-crt-") or low.startswith("api-ms-win-core-"):
            shutil.copy2(os.path.join(DOWNLEVEL, name), pydir)
            n += 1
    print(f"   {n} DLL")

    step("Thư viện (pip --target, win_amd64 cp311)")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "--no-compile", "--target",
                           os.path.join(DIST, "lib"), "--platform", "win_amd64", "--python-version", "3.11",
                           "--implementation", "cp", "--abi", "cp311", "--only-binary=:all:",
                           "-r", os.path.join(BOT, "requirements-netops.txt")])

    step("Mã nguồn bot")
    app = os.path.join(DIST, "app")
    os.makedirs(app)
    for item in APP_ITEMS:
        src = os.path.join(BOT, item)
        dst = os.path.join(app, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(src, dst)
    # CRLF: Notepad trên Server 2012 R2 hiển thị file LF thành một dòng duy nhất
    with open(os.path.join(BOT, "deploy", "windows", "env.netops"), encoding="utf-8") as f:
        env = f.read()
    with open(os.path.join(app, ".env"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(env)
    # configs/ của Site 100 (đã che bí mật) để /backup, /drift so lệch ngay trên máy chủ
    shutil.copytree(os.path.join(BOT, "..", "..", "configs", "01-Site100-Campus"),
                    os.path.join(DIST, "configs", "01-Site100-Campus"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "test"))
    for f in ("run.cmd",):
        shutil.copy2(os.path.join(BOT, "deploy", "windows", f), DIST)
    # PowerShell 4 (2012 R2) chỉ đọc UTF-8 đúng khi có BOM
    with open(os.path.join(BOT, "deploy", "windows", "install.ps1"), encoding="utf-8") as f:
        ps = f.read()
    with open(os.path.join(DIST, "install.ps1"), "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(ps)

    os.makedirs(os.path.join(DIST, "secrets"))
    os.makedirs(os.path.join(DIST, "logs"))
    if a.with_secrets:
        step("secrets/credentials.md (chỉ netops + vManage)")
        src = os.path.expanduser(r"~/.claude/campus-lab-credentials.md")
        rows = ["| Thiết bị | Tài khoản | Mật khẩu | Ghi chú |", "|---|---|---|---|"]
        with open(src, encoding="utf-8") as f:
            for line in f:
                if line.startswith("|") and any(t in line for t in SECRET_TAGS):
                    rows.append(line.rstrip("\n"))
        missing = [t for t in SECRET_TAGS if not any(t in r for r in rows)]
        if missing:
            sys.exit(f"Thiếu dòng credentials: {missing}")
        with open(os.path.join(DIST, "secrets", "credentials.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")
        print(f"   {len(rows) - 2} dòng")

    size = sum(os.path.getsize(os.path.join(d, x)) for d, _, fs in os.walk(DIST) for x in fs)
    print(f"Xong: {DIST}  ({size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
