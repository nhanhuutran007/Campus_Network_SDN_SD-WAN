"""Thay đổi cấu hình từ dòng lệnh (cho người vận hành có quyền vào máy chạy bot):

    python scripts/change_cli.py SW-S500 "interface Loopback99" " description test" --reason "thử"
    python scripts/change_cli.py ... --yes          # bỏ bước gõ 'yes' (kịch bản kiểm thử)
    python scripts/change_cli.py --undo <id>        # chỉ trong cùng tiến trình — dùng Telegram /undo cho thực tế

Quy trình giống hệt Telegram: kiểm lệnh → xem trước → duyệt → áp → kiểm sau → tự rollback.
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
from campus import service  # noqa: E402
from campus.change import ChangeError  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("device")
    ap.add_argument("commands", nargs="+")
    ap.add_argument("--reason", default="")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--undo", action="store_true", help="hoàn tác ngay sau khi thay đổi đạt (kiểm thử)")
    a = ap.parse_args()
    who = f"cli:{getpass.getuser()}"
    mgr = service.changes()
    try:
        req = mgr.propose(a.device, a.commands, a.reason, who)
    except ChangeError as e:
        sys.exit(f"LỖI: {e}")
    print(req.card())
    if not a.yes and input("\nGõ 'yes' để duyệt: ").strip() != "yes":
        mgr.cancel(req.id, who)
        sys.exit("Đã huỷ.")
    req = mgr.approve_and_run(req.id, who, progress=lambda m: print("  ·", m))
    print(f"\nKẾT QUẢ #{req.id}: {req.status}")
    if a.undo and req.status == "done":
        req = mgr.undo(req.id, who, progress=lambda m: print("  ·", m))
        print(f"SAU HOÀN TÁC: {req.status}")
    sys.exit(0 if req.status in ("done", "undone") else 1)


if __name__ == "__main__":
    main()
