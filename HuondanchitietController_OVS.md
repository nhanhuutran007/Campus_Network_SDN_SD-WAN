# Hướng Dẫn Chi Tiết Cấu Hình Ryu Controller & Open vSwitch (OVS)

Tài liệu này ghi chú lại toàn bộ quá trình thiết lập mạng Control Plane giữa Ryu Controller và Open vSwitch (OVS) trên môi trường ảo hóa EVE-NG, cũng như cách khắc phục lỗi tương thích phiên bản thư viện Python.

---

## PHẦN 1: BẢO LƯU CẤU HÌNH SAU KHI KHỞI ĐỘNG LẠI (PERSISTENCE)

Lệnh cấu hình IP bằng lệnh `ip addr add` chỉ có tác dụng tạm thời trong phiên làm việc hiện tại. Khi khởi động lại máy ảo (Reboot), cấu hình IP sẽ bị mất. 
*(Riêng các lệnh cấu hình của OVS bằng `ovs-vsctl` thì đã được lưu tự động vào `conf.db`, nên Bridge `br0` không bị mất).*

Để duy trì mạng, bạn cần áp dụng cấu hình vĩnh viễn hoặc tạo Script chạy tự động như sau:

### 1.1 Trên máy ảo Ubuntu (SDN Controller)
Ubuntu 20.04 sử dụng công cụ `Netplan` để quản lý mạng.
1. Mở file cấu hình Netplan (Tên file có thể thay đổi tùy hệ thống, dùng phím Tab để gợi ý):
   ```bash
   sudo nano /etc/netplan/00-installer-config.yaml
   ```
2. Thêm cấu hình IP tĩnh cho card mạng `ens4` (Cổng giao tiếp với OVS):
   ```yaml
   network:
     ethernets:
       ens3:
         dhcp4: true  # Dành cho cổng ra Internet tải gói
       ens4:
         addresses: [192.168.100.1/24]
         dhcp4: false
     version: 2
   ```
3. Nhấn `Ctrl+O` -> `Enter` để lưu, `Ctrl+X` để thoát.
4. Áp dụng cấu hình:
   ```bash
   sudo netplan apply
   ```

**Tạo Script để bật nhanh Ryu Controller:**
Khi bật Lab lên, bạn vẫn phải gõ lệnh chạy Ryu, nên hãy viết một bash script cho lẹ:
```bash
echo "ryu-manager simple_switch_13.py" > start_ryu.sh
chmod +x start_ryu.sh
```
*Mỗi lần bật Lab, bạn chỉ cần gõ `./start_ryu.sh` là Controller sẽ chạy.*

### 1.2 Trên máy ảo OVS (AccessTest)
Cách nhanh nhất và ít rủi ro nhất đối với các node Linux nhỏ trong EVE-NG là tạo một Script gán IP tự động:
1. Tạo file bash:
   ```bash
   nano setup_network.sh
   ```
2. Nhập nội dung sau:
   ```bash
   #!/bin/bash
   # Bật các cổng và gán IP cho Control Plane
   ip link set eth1 up
   ip addr add 192.168.100.2/24 dev eth1
   # Bật các cổng Data Plane kết nối với máy trạm
   ip link set eth2 up
   ip link set eth3 up
   ```
3. Cấp quyền thực thi: `chmod +x setup_network.sh`.
*Từ nay về sau, mỗi khi bật máy ảo OVS lên, bạn gõ `./setup_network.sh` là mạng sẽ thông suốt.*

---

## PHẦN 2: LỊCH SỬ CÀI ĐẶT VÀ FIX LỖI (DÀNH CHO VIỆC CÀI LẠI TỪ ĐẦU)

Dưới đây là các lệnh đã được sử dụng để cài đặt thành công hệ thống (Lưu lại để báo cáo hoặc làm tài liệu khôi phục).

### Bước 1: Khởi tạo mạng Control Plane
- **SDN Controller (Cổng e1/ens4):** IP `192.168.100.1/24`
- **OVS (Cổng e1/eth1):** IP `192.168.100.2/24`

### Bước 2: Cài đặt Ryu Controller và sửa lỗi thư viện
Do Ryu chưa tương thích hoàn toàn với các phiên bản thư viện Python mới nhất, cần cài đặt và hạ cấp 2 thư viện `netaddr` và `eventlet` để tránh lỗi `RuntimeError: Python 3.7.0 or higher is required!` và `ImportError: cannot import name 'ALREADY_HANDLED'`.

```bash
sudo apt update
sudo apt install -y gcc python3-dev libffi-dev libssl-dev python3-pip wget
pip3 install ryu
pip3 install netaddr==0.8.0
pip3 install eventlet==0.30.2
```

### Bước 3: Tải mã nguồn ứng dụng và khởi chạy Controller
Sử dụng file chuyển mạch Layer 2 hỗ trợ OpenFlow 1.3:
```bash
wget https://raw.githubusercontent.com/faucetsdn/ryu/master/ryu/app/simple_switch_13.py
ryu-manager simple_switch_13.py
```

### Bước 4: Cấu hình OVS và trỏ về Controller
- Gom các cổng `eth2`, `eth3` (cổng PC) vào Switch ảo.
- KHÔNG thêm cổng `eth1` (cổng Control Plane) vào Switch ảo.
- Ép OVS dùng OpenFlow 1.3 và trỏ tới Controller qua port 6653.

```bash
ovs-vsctl add-br br0
ovs-vsctl add-port br0 eth2
ovs-vsctl add-port br0 eth3
ovs-vsctl set bridge br0 protocols=OpenFlow13
ovs-vsctl set-controller br0 tcp:192.168.100.1:6653
```

### Bước 5: Kiểm tra kết nối
```bash
ovs-vsctl show
```
Kết quả báo `is_connected: true` bên dưới cấu hình Controller là OVS đã sẵn sàng chuyển tiếp gói tin (Data Plane). Mọi luồng đi qua PC sẽ được truy vấn Flow Table tại Controller.

---

## PHẦN 3: SDN QUẢN LÝ TOÀN BỘ L2 CAMPUS (Dist/Access-SW) — TỪ 08/2026

> **Lưu ý (04/08/2026)**: node test cũ AccessTest + VPC11/12 đã **xóa khỏi lab** — PHẦN 1–2 dưới đây giữ làm tài liệu gốc về cách cài Ryu/OVS (dải test 192.168.100.0/24 không còn dùng).
> **Lưu ý (07/08/2026)**: control plane SDN **chuyển sang VLAN 99 MANAGEMENT** (bỏ link riêng, mạng cũ 10.1.100.0/24 đã xóa khỏi lab) — đúng kiến trúc doanh nghiệp: controller nối vào mạng quản trị chung, không kéo dây riêng tới từng switch; dùng các bước ở 3.3 bên dưới.

### 3.1. Sơ đồ kết nối control plane (VLAN 99 MANAGEMENT — dải 10.1.99.0/24)

| Switch | Cổng control (IP mgmt trong VLAN 99) | Controller trỏ về |
|---|---|---|
| SDN_CONTROLLER (e0) | 10.1.99.10/24 (→ SwitchServerFarm e1/0, access VLAN 99) | — (là controller) |
| Dist-SW1 / Dist-SW2 (dpid 5, 8) | 10.1.99.11 / 10.1.99.12 | tcp:10.1.99.10:6653 |
| Access-SW1 / Access-SW2 (dpid 68, 66) | 10.1.99.21 / 10.1.99.22 | tcp:10.1.99.10:6653 |
| Access-SW3 / Access-SW4 (dpid 70, 69) | 10.1.99.23 / 10.1.99.24 | tcp:10.1.99.10:6653 |

(Không có link riêng: kênh OpenFlow đi trên VLAN 99 MANAGEMENT qua các link uplink sẵn có — Dist/Access có sẵn IP mgmt VLAN 99. Controller chỉ cắm 1 cổng e0 vào SwitchServerFarm; e3 = Cloud-NAT cho Internet.)

### 3.2. App Ryu mới — `campus_switch_13.py`

Thay thế `simple_switch_13.py` (không xử lý VLAN nên không dùng được cho campus):

```bash
cp campus_switch_13.py /root/ryu-app/
ryu-manager --ofp-tcp-listen-port 6653 /root/ryu-app/campus_switch_13.py ryu.app.ofctl_rest
```

- **L2 nhận thức VLAN**: học MAC theo (VLAN, MAC, port); flood đúng VLAN (port access dùng `tag=` của OVS — OVS tự push/pop VLAN); chưa biết đích mới gửi `packet-in` lên controller (reactive).
- **ACL proactive**: `BLOCK_PORTS` trong app — flow drop priority 40000 tự cài khi switch kết nối. Mặc định danh sách rỗng để mọi VPC dùng DHCP; có thể thêm VPC14 / Access-SW1 `ens6` khi cần demo chặn.
- **Northbound**: `ofctl_rest` mở REST port 8080 → `curl http://127.0.0.1:8080/stats/switches` trả `[5, 8, 68, 66, 70, 69]`; cài flow từ xa bằng `POST /stats/flowentry/add` (xem demo cuối file app).

### 3.3. Các bước bổ sung trên OVS campus (trong script `.sh` của từng node)

```bash
# 1) IP management/control plane trong VLAN 99 (bridge br-mgmt dùng chung)
ip addr add 10.1.99.<x>/24 dev br-mgmt   # x: Dist .11/.12, Access .21–.24

# 2) Ép OpenFlow 1.3 + khai datapath-id cố định (bằng node-id)
ovs-vsctl set bridge br0 protocols=OpenFlow13
ovs-vsctl set bridge br0 other_config:datapath-id=00000000000000<node-id hex>

# 3) Trỏ controller (IP VLAN 99 của SDN_CONTROLLER — dùng chung cho mọi switch)
ovs-vsctl set-controller br0 tcp:10.1.99.10:6653

# 4) Chỉ chuyển tiếp theo flow của controller; app phải có table-miss priority 0
ovs-vsctl set bridge br0 fail_mode=secure

# 5) Tắt OVS STP để frame đi vào OpenFlow pipeline và sinh packet-in
ovs-vsctl set bridge br0 stp_enable=false
```

> **Lưu ý quan trọng**: không xóa cấu hình `tag=`/`trunks=` trong script switch. Với `fail_mode=secure`, app `campus_switch_13.py` phải cài table-miss priority 0; nếu thiếu rule này, ARP/broadcast chưa khớp flow sẽ bị drop trước khi Ryu nhận `packet-in`.
