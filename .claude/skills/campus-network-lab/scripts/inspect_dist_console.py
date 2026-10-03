import os
import re
import sys
import time
import telnetlib


def clean(data):
    data = data.replace(b"\x00", b"")
    return re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", data)


def run(port, commands, wait=3.0):
    session = telnetlib.Telnet("10.215.28.26", port, timeout=8)
    time.sleep(1.5)
    output = b""
    for _ in range(3):
        session.write(b"\r")
        time.sleep(1)
        chunk = clean(session.expect([b"eve@ovs", b"ovs login:"], timeout=5)[2])
        output += chunk
        if b"eve@ovs" in chunk:
            break
        if b"ovs login:" in chunk:
            session.write(b"eve\r")
            session.expect([b"Password:"], timeout=4)
            session.write(b"eve\r")
            output += clean(session.expect([b"eve@ovs"], timeout=7)[2])
            break
    for command in commands:
        marker = f"__DONE_{time.time_ns()}__"
        session.write((command + f"; echo {marker}\r").encode())
        _, _, chunk = session.expect([marker.encode()], timeout=wait)
        output += clean(chunk)
    session.close()
    return output.decode("utf-8", "replace")


commands = [
    "hostname",
    "sudo systemctl status campus-ovs-restore.service --no-pager -l",
    "sudo journalctl -u campus-ovs-restore.service -b --no-pager -n 80",
    "sudo ovs-vsctl show",
    "sudo ovs-vsctl get Controller br0 is_connected",
    "sudo ovs-ofctl -O OpenFlow13 dump-flows br0 | grep priority=50000",
]
for port, name in ((33541, "Dist-SW1"), (33544, "Dist-SW2")):
    print(f"=== {name} port {port} ===", flush=True)
    print(run(port, commands, wait=12)[-9000:], flush=True)
