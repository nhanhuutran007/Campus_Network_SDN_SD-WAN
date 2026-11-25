"""Kiểm thử live một lệnh chỉ-đọc, không qua LLM:

    python scripts/smoke_console.py Core-SW1 "show ip interface brief"
    python scripts/smoke_console.py vEdge1-S300 "show bfd sessions"
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.stdout.reconfigure(encoding="utf-8")
from campus import service  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    res = service.run_command(sys.argv[1], " ".join(sys.argv[2:]))
    print(res)
    sys.exit(0 if res.ok else 1)
