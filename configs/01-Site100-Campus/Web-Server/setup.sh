#!/usr/bin/env bash
set -Eeuo pipefail

# Cau hinh co ban cho Web-Server (EVE-NG node 22).
# Chay bang: sudo bash setup.sh

readonly HOST_NAME="web-server"
readonly INTERFACE="eth0"
readonly IPV4_CIDR="10.1.1.10/28"
readonly GATEWAY="10.1.1.1"
readonly DNS_SERVERS="1.1.1.1, 8.8.8.8"
readonly NETPLAN_FILE="/etc/netplan/99-campus-web-server.yaml"
readonly WEB_ROOT="/var/www/html"

if [[ ${EUID} -ne 0 ]]; then
  echo "ERROR: run this script with sudo/root." >&2
  exit 1
fi

if [[ ! -e "/sys/class/net/${INTERFACE}" ]]; then
  echo "ERROR: interface ${INTERFACE} does not exist." >&2
  exit 1
fi

hostnamectl set-hostname "${HOST_NAME}"
if grep -Eq '^127\.0\.1\.1[[:space:]]+' /etc/hosts; then
  sed -i -E "s/^127\.0\.1\.1[[:space:]].*/127.0.1.1 ${HOST_NAME}/" /etc/hosts
else
  printf '127.0.1.1 %s\n' "${HOST_NAME}" >> /etc/hosts
fi

install -d -m 0755 /etc/netplan
cat > "${NETPLAN_FILE}" <<EOF
network:
  version: 2
  renderer: NetworkManager
  ethernets:
    ${INTERFACE}:
      dhcp4: false
      dhcp6: false
      addresses:
        - ${IPV4_CIDR}
      gateway4: ${GATEWAY}
      nameservers:
        addresses: [${DNS_SERVERS}]
EOF
chmod 0600 "${NETPLAN_FILE}"

netplan generate

if ip -4 -o address show dev "${INTERFACE}" | grep -Fq "${IPV4_CIDR}" \
    && ip -4 route show default | grep -Eq "^default via ${GATEWAY} dev ${INTERFACE}([[:space:]]|$)"; then
  echo "Network settings are already active; skipping netplan apply."
else
  netplan apply
fi

for _ in {1..15}; do
  if ip -4 -o address show dev "${INTERFACE}" | grep -Fq "${IPV4_CIDR}"; then
    break
  fi
  sleep 1
done

if ! ip -4 -o address show dev "${INTERFACE}" | grep -Fq "${IPV4_CIDR}"; then
  echo "ERROR: static address ${IPV4_CIDR} was not applied." >&2
  exit 1
fi

install -d -m 0755 "${WEB_ROOT}"
cat > "${WEB_ROOT}/index.html" <<'EOF'
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Campus Network DMZ Web Server</title>
  <style>
    body { max-width: 760px; margin: 12vh auto; padding: 0 24px; font: 18px/1.6 sans-serif; color: #172033; }
    main { border-left: 6px solid #1677ff; padding: 10px 24px; background: #f5f8fc; }
    code { color: #075985; }
  </style>
</head>
<body>
  <main>
    <h1>Campus Network DMZ</h1>
    <p>Web-Server node 22 dang hoat dong tren <code>10.1.1.10</code>.</p>
  </main>
</body>
</html>
EOF

export DEBIAN_FRONTEND=noninteractive
if ! command -v nginx >/dev/null 2>&1; then
  if apt-get \
      -o Acquire::Retries=0 \
      -o Acquire::http::Timeout=10 \
      -o Acquire::https::Timeout=10 \
      update \
    && apt-get \
      -o Acquire::Retries=0 \
      -o Acquire::http::Timeout=10 \
      -o Acquire::https::Timeout=10 \
      install -y nginx curl ca-certificates; then
    echo "Nginx installed from the Ubuntu repository."
  else
    echo "WARNING: Ubuntu repository is unreachable; using Python HTTP fallback." >&2
  fi
fi

if command -v nginx >/dev/null 2>&1; then
  if systemctl list-unit-files --no-legend campus-web-demo.service 2>/dev/null \
      | grep -q '^campus-web-demo\.service'; then
    systemctl disable --now campus-web-demo.service || true
  fi
  nginx -t
  systemctl enable nginx
  systemctl restart nginx
  WEB_SERVICE="nginx"
else
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: neither Nginx nor Python 3 is available." >&2
    exit 1
  fi
  cat > /etc/systemd/system/campus-web-demo.service <<EOF
[Unit]
Description=Campus Network DMZ HTTP fallback
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${WEB_ROOT}
ExecStart=/usr/bin/python3 -m http.server 80 --bind 0.0.0.0
Restart=on-failure
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable campus-web-demo.service
  systemctl restart campus-web-demo.service
  WEB_SERVICE="campus-web-demo"
fi

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q '^Status: active'; then
  ufw allow 80/tcp
fi

if command -v curl >/dev/null 2>&1; then
  curl -fsS --max-time 5 http://127.0.0.1/ >/dev/null
else
  python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1/", timeout=5).read(1)'
fi

echo "WEB_SERVER_SETUP_OK"
echo "hostname=$(hostname)"
echo "address=${IPV4_CIDR}"
echo "gateway=${GATEWAY}"
echo "web_service=${WEB_SERVICE}"
