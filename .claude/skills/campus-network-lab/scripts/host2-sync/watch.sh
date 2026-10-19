#!/bin/bash
# one watcher: new chunk lines/errors from big33.log + VPN/host transitions; exits by itself after 29 min (no leaked loops)
cd "$(dirname "$0")"
end=$(( $(date +%s) + 1740 ))
up() { timeout 8 bash -c "</dev/tcp/$1/22" 2>/dev/null && echo UP || echo DOWN; }
n=$(wc -l < big33.log); p1=UP; p2=UP
while [ "$(date +%s)" -lt "$end" ]; do
  m=$(wc -l < big33.log)
  if [ "$m" -gt "$n" ]; then
    tail -n +$((n + 1)) big33.log | head -n $((m - n)) | grep -E "chunk [0-9]+/49|MISMATCH|retry|FAILED|FILE-|RESUME|Traceback|Error"
    n=$m
  fi
  s1=$(up 10.215.28.26); s2=$(up 10.0.227.112)
  if [ "$s1" != "$p1" ] || [ "$s2" != "$p2" ]; then
    l="$(date '+%d/%m %H:%M:%S') host1(VPN)=$s1 host2=$s2 | virtiob xong $(grep -cE 'chunk [0-9]+/49 (OK|da co san)' big33.log)/49 đoạn; log cuối: $(tail -1 big33.log)"
    echo "$l" >> vpn_progress.log; echo "$l"; p1=$s1; p2=$s2
  fi
  grep -q "FILE-.*virtiob" big33.log && exit 0
  sleep 30
done
echo "watch: hết 29 phút, cần bật lại ($(date '+%H:%M'))"
