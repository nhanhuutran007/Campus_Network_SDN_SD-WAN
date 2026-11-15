"""runsrv.py <script.py> <tag1,tag2,...> [tham so...] : chay script do tren server EVE, tach khoi SSH.

Chay tren laptop. Chep script (va scon.py) len /root/loadtest, dua mat khau cua cac tag qua stdin dang JSON
(khong nam trong dong lenh, khong luu file), ghi dau ra vao /root/loadtest/<ten>.out. Script tiep tuc chay
ke ca khi laptop mat ket noi.
"""
import json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "host2-sync"))
from eve import client, password

script, tags, args = sys.argv[1], [t for t in sys.argv[2].split(",") if t], sys.argv[3:]
name = os.path.splitext(os.path.basename(script))[0]
c = client("h1")
sf = c.open_sftp()
for f in (os.path.join(HERE, "scon.py"), script):
    sf.put(f, "/root/loadtest/" + os.path.basename(f))
sf.close()
cmd = "cd /root/loadtest && nohup python3 -u %s.py %s > %s.out 2>&1" % (name, " ".join("'%s'" % a for a in args), name)
i, o, e = c.exec_command(cmd)
i.write(json.dumps({t: password(t) for t in tags}) + "\n")
i.flush()
i.channel.shutdown_write()
time.sleep(3)
print("da chay tren server:", name, "-> /root/loadtest/%s.out" % name)
c.close()
