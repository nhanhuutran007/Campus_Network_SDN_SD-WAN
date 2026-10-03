"""deploy_node9.py <local_file>=<path_in_vm> [...] [--backup] [--no-restart]

Nap file vao dia SDN_CONTROLLER (node 9, host 1) khi KHONG co SSH vao VM:
  1) SFTP file len host 1 (/tmp/campus-deploy/), so md5
  2) unl_wrapper stop node 9, cho qemu thoat han (kiem /proc/*/cwd)
  3) guestfish upload (tuy chon --backup: cp <dich> <dich>.bak-<ngay> truoc)
  4) so md5 trong dia voi ban local, roi start node 9

Vi du (Git Bash can MSYS_NO_PATHCONV=1):
  MSYS_NO_PATHCONV=1 python deploy_node9.py configs/01-Site100-Campus/campus_switch_13.py=/root/ryu-app/campus_switch_13.py
OVS giu flow (fail_mode=secure) trong luc node 9 tat -> du lieu van chay.
Mat khau doc tu file credentials luc chay (qua eve.py), khong in ra.
"""
import hashlib
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "host2-sync"))
from eve import client  # noqa: E402

LAB = "/opt/unetlab/labs/TranHuuNhan-PKT/Campus Network SDN SD-WAN.unl"
NODE_DIR = "/opt/unetlab/tmp/6/ecf7c5b8-8c91-4616-953e-10b367b388e6/9"
WRAP = "/opt/unetlab/wrappers/unl_wrapper"
STAGE = "/tmp/campus-deploy"


def run(c, cmd, timeout=300):
    _, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode(errors="replace")
    err = e.read().decode(errors="replace")
    return out + "\n".join(l for l in err.splitlines() if "mesg:" not in l)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    backup = "--backup" in sys.argv
    restart = "--no-restart" not in sys.argv
    pairs = []
    for a in args:
        src, dst = a.split("=", 1)
        if not dst.startswith("/") or ":" in dst or " " in dst:
            # Git Bash doi '=/root/..' thanh 'C:/Program Files/Git/root/..' -> chay voi MSYS_NO_PATHCONV=1
            sys.exit("duong dan dich sai (%s) - Git Bash: dat MSYS_NO_PATHCONV=1" % dst)
        md5 = hashlib.md5(open(src, "rb").read()).hexdigest()
        pairs.append((src, dst, md5))
    if not pairs:
        sys.exit(__doc__)
    c = client("h1")
    sftp = c.open_sftp()
    run(c, "mkdir -p %s" % STAGE)
    for src, dst, md5 in pairs:
        staged = "%s/%s" % (STAGE, os.path.basename(dst))
        sftp.put(src, staged)
        rmd5 = run(c, "md5sum '%s'" % staged).split()[0]
        print("upload %-40s md5 %s %s" % (os.path.basename(src), md5, "OK" if rmd5 == md5 else "MISMATCH " + rmd5))
        if rmd5 != md5:
            sys.exit(1)
    print(run(c, "timeout 60 %s -a stop -T 6 -F '%s' -D 9 </dev/null >/dev/null 2>&1; echo stop rc=$?" % (WRAP, LAB)).strip())
    for i in range(40):
        busy = run(c, "for p in /proc/[0-9]*; do [ \"$(readlink $p/cwd 2>/dev/null)\" = '%s' ] && "
                      "grep -q qemu $p/comm 2>/dev/null && echo busy; done" % NODE_DIR).strip()
        if not busy:
            break
        time.sleep(2)
    else:
        sys.exit("qemu node 9 khong thoat - dung lai, khong ghi dia")
    stamp = time.strftime("%Y%m%d-%H%M")
    gf = []
    for src, dst, md5 in pairs:
        if backup:
            gf.append("-cp %s %s.bak-%s" % (dst, dst, stamp))     # '-' : bo qua loi neu chua co file
        gf.append("upload %s/%s %s" % (STAGE, os.path.basename(dst), dst))
    for src, dst, md5 in pairs:
        gf.append("checksum md5 %s" % dst)
    out = run(c, "LIBGUESTFS_BACKEND=direct timeout 180 guestfish -a %s/virtioa.qcow2 -i <<'GF'\n%s\nGF\necho gf_rc=$?"
              % (NODE_DIR, "\n".join(gf)))
    sums = [l.strip() for l in out.splitlines() if len(l.strip()) == 32]
    ok = sums == [m for _, _, m in pairs]
    print("guestfish:", "md5 khop" if ok else "LOI\n" + out)
    if restart:
        print(run(c, "timeout 80 %s -a start -T 6 -F '%s' -D 9 </dev/null >/dev/null 2>&1; sleep 2; "
                     "ss -tln | grep -q ':33545 ' && echo 'node 9 LISTEN' || echo 'node 9 NOT LISTEN'" % (WRAP, LAB)).strip())
    c.close()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
