#!/bin/bash
set -u

controller="http://10.1.99.10:8080"
echo "=== TIME ==="
date -u '+%Y-%m-%dT%H:%M:%SZ'
echo "=== RYU SWITCHES ==="
curl -fsS --max-time 5 "$controller/stats/switches" || echo "REST_FAILED"
echo

for dpid in 5 8 68 66 70 69; do
    echo "=== FLOW DPID $dpid ==="
    curl -fsS --max-time 5 "$controller/stats/flow/$dpid" || echo "FLOW_FAILED"
    echo
done

echo "=== EVE OVS NODE CONSOLE PORTS ==="
for node in 5 8 68 66 70 69; do
    port=$((33536 + node))
    if ss -ltn | grep -q ":${port} "; then
        echo "node=$node port=$port state=LISTEN"
    else
        echo "node=$node port=$port state=NOT_LISTEN"
    fi
done
