#!/bin/sh
# Cài Nginx + cổng thông tin nội bộ vào đĩa Web-Server (node 22) khi VM đang TẮT.
# Chạy trên host EVE bằng virt-customize (không cần Internet trong VM):
#   virt-customize -a <tmp>/22/virtioa.qcow2 \
#     --copy-in <staging>/debs:/root --copy-in <staging>/web:/root \
#     --run /root/web/offline-install.sh
# Gói: nginx-light, nginx-common, libnginx-mod-http-echo (bionic-updates 1.14.0-0ubuntu1.11).
set -e

dpkg -i /root/debs/*.deb || true
dpkg --configure -a

# Chứng chỉ tự ký cho www.campus.internal (10 năm, có SAN để trình duyệt khớp tên)
# (.internal: TLD ICANN dành cho mạng riêng; .local là của mDNS nên đã bỏ)
install -d -m 0755 /etc/ssl/campus
if [ ! -f /etc/ssl/campus/www.campus.internal.key ]; then
  cat > /etc/ssl/campus/www.cnf <<'CNF'
[req]
distinguished_name = dn
x509_extensions = ext
prompt = no
[dn]
C = VN
O = Campus Network
CN = www.campus.internal
[ext]
subjectAltName = DNS:www.campus.internal, DNS:web.campus.internal, IP:10.1.1.10
basicConstraints = CA:FALSE
CNF
  openssl req -x509 -nodes -newkey rsa:2048 -days 3650 -config /etc/ssl/campus/www.cnf \
    -keyout /etc/ssl/campus/www.campus.internal.key \
    -out /etc/ssl/campus/www.campus.internal.crt
  chmod 0600 /etc/ssl/campus/www.campus.internal.key
fi

install -d -m 0755 /var/www/campus
install -m 0644 /root/web/index.html /var/www/campus/index.html
install -d -m 0755 /var/www/setup
for f in /root/web/setup/*; do [ -f "$f" ] && install -m 0644 "$f" /var/www/setup/; done
install -m 0644 /root/web/campus-intranet.conf /etc/nginx/sites-available/campus-intranet.conf
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/campus-intranet.conf /etc/nginx/sites-enabled/campus-intranet.conf
nginx -t

# Tắt dịch vụ Python dự phòng của setup.sh (nếu có), bật Nginx lúc khởi động
systemctl disable campus-web-demo.service 2>/dev/null || true
rm -f /etc/systemd/system/multi-user.target.wants/campus-web-demo.service
systemctl enable nginx

# DNS nội bộ + gửi log hệ thống về Syslog-Server
sed -i 's/addresses: \[1.1.1.1, 8.8.8.8\]/addresses: [10.1.90.10]\n        search: [campus.internal]/' /etc/netplan/99-campus-web-server.yaml
sed -i 's/search: \[campus.local\]/search: [campus.internal]/' /etc/netplan/99-campus-web-server.yaml
printf '*.info @10.1.90.11:514\n' > /etc/rsyslog.d/60-campus-syslog.conf

rm -rf /root/debs /root/web
echo OFFLINE_INSTALL_OK
