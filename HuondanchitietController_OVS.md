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
