# Cấu hình thiết bị cho lab EVE-NG — Campus Network SDN + SD-WAN

Bộ file cấu hình startup cho từng node trong lab `Campus Network SDN SD-WAN.unl`.
Sinh trực tiếp từ bảng quy hoạch IP trong `campus_network_sdn_sdwan.md` (mục 2.1, 2.2, 2.3, 2.4).

---

## 1. Cấu trúc thư mục

```
configs/
├── README.md                  ← file này
├── 01-Site100-Campus/         ← Core, FW, Server Farm, DMZ, vEdge, VPC, script OVS
├── 02-Site200-CanTho/         ← Brand-FW, vEdge1/2, SwitchBrand, SW55/56, VPC
├── 03-Site300-DaNang/         ← Brand-FW, vEdge1/2, SwitchBrand, SW58/59, VPC
├── 04-Site400-NhaTrang/       ← Brand-FW, vEdge1/2, SwitchBrand, SW60/57, VPC
├── 05-Site900-Controller/     ← Switch32, Switch61, vEdge65
└── 06-ServiceProvider/        ← Internet, MPLS
```

Mỗi thư mục thiết bị chứa `config.cfg` (hoặc `config.txt` cho VPC, `.sh` cho node Linux/OVS).

## 2. Bảng ánh xạ tên thiết bị → Node ID trong EVE-NG

> Đường dẫn upload: `/opt/unetlab/labs/<user>/Campus Network SDN SD-WAN/<node-id>/`
> (thay `<user>` bằng tài khoản trên server EVE, thường là `root`).

| Thiết bị (thư mục trong repo) | Node ID | Template |
|---|---|---|
| FW-ASAv-Active | 1 | asav |
| FW-ASAv-Standby | 2 | asav |
| Core-SW1 | 3 | viosl2 |
| Core-SW2 | 4 | viosl2 |
| Dist-SW1 | 5 | linux (OVS script) |
| vEdge2-S100 | 6 | vtedge |
| SwitchDMZ | 7 | iol |
| Dist-SW2 | 8 | linux (OVS script) |
| SDN_CONTROLLER | 9 | linux (OVS script) |
| AccessTest | 10 | linux (OVS script) |
| VPC11 | 11 | vpcs |
| VPC12 | 12 | vpcs |
| Mail-Server | 13 | win (cấu hình tay) |
| VPC14 | 14 | vpcs |
| VPC15 | 15 | vpcs |
| VPC16 | 16 | vpcs |
| VPC17 | 17 | vpcs |
| VPC18 | 18 | vpcs |
| VPC19 | 19 | vpcs |
| VPC20 | 20 | vpcs |
| VPC21 | 21 | vpcs |
| Web-Server | 22 | win (cấu hình tay) |
| DHCP-Server | 23 | win (cấu hình tay) |
| SwitchServerFarm | 24 | iol |
| Syslog-Server | 25 | win (cấu hình tay) |
| Internet | 26 | vios |
| MPLS | 27 | vios |
| vEdge1-S100 | 28 | vtedge |
| vEdge1-S200 | 29 | vtedge |
| vEdge1-S300 | 30 | vtedge |
| vEdge1-S400 | 31 | vtedge |
| Switch32 | 32 | iol |
| vManager | 33 | vtmgmt (cấu hình qua vManage GUI) |
| vSmart | 34 | vtsmart (cấu hình qua vManage) |
| vBond | 35 | vtbond (cấu hình qua vManage) |
| Win (quản trị) | 36 | win (cấu hình tay) |
| Brand-FW-S200 | 37 | asav |
| Brand-FW-S400 | 38 | asav |
| Brand-FW-S300 | 39 | asav |
| vEdge2-S300 | 40 | vtedge |
| vEdge2-S400 | 41 | vtedge |
| vEdge2-S200 | 42 | vtedge |
| VPC43–VPC54 | 43,44,45,46,47,48,49,50,51,52,53,54 | vpcs |
| SW55, SW56, SW57, SW58, SW59, SW60 | 55,56,57,58,59,60 | iol |
| Switch61 | 61 | iol |
| SwitchBrand-S300 | 62 | iol |
| SwitchBrand-S200 | 63 | iol |
| SwitchBrand-S400 | 64 | iol |
| vEdge65 | 65 | vtedge |
| Access-SW2 | 66 | linux (OVS script) |
| Access-SW1 | 68 | linux (OVS script) |
| Access-SW4 | 69 | linux (OVS script) |
| Access-SW3 | 70 | linux (OVS script) |

## 3. Cách nạp config vào EVE-NG

### Cách A — Đặt file vào thư mục lab trên server EVE (khuyến nghị)

1. Upload file của từng thiết bị về đúng thư mục node trên server EVE:

   ```
   scp configs/01-Site100-Campus/Core-SW1/config.cfg root@<eve-ip>:/opt/unetlab/labs/<user>/Campus\ Network\ SDN\ SD-WAN/3/config.cfg
   ```

2. Trong file `.unl` trên server, node đã được bật `config="1"` (file `.unl` trong repo đã sửa sẵn — nếu lab đang chạy, dùng bản trên server đã được chỉnh hoặc sửa tay: chuột phải node → **Edit** → tích **Config**).
3. Tắt node (Power off) rồi **Wipe** và khởi động lại — EVE nạp config khi boot.

> Với node đang **chạy**: EVE giữ file config ở `/opt/unetlab/tmp/...` — an toàn nhất là wipe node sau khi đặt file ở `/opt/unetlab/labs/...`.

### Cách B — Dán qua console (telnet) — áp dụng cho mọi thiết bị

- EVE cung cấp cổng telnet: `telnet <eve-ip> <port-console>` (port hiển thị khi double-click node).
- Với IOS/IOL: dán từng khối lệnh sau dấu `#`.
- Với ASAv: vào `configure terminal` rồi dán.
- Với **vEdge**: EVE không đảm bảo tự nạp `config.cfg` cho vtedge. Cách chắc chắn: sau lần boot đầu (onboarding đặt password), vào `config` mode rồi dán nội dung `config.cfg`.
- Với node Linux/OVS: copy script vào VM rồi chạy `bash script.sh` (xem mục 5).

## 4. Ghi chú từng loại thiết bị

| Loại | File | Nạp tự động khi boot? |
|---|---|---|
| viosl2 / vios (Core, Internet, MPLS) | `config.cfg` | ✅ (cần `config="1"`) |
| iol (SW55–61, SwitchBrand, SwitchDMZ, SwitchServerFarm) | `config.cfg` | ✅ (cần `config="1"`) |
| asav (FW-ASAv, Brand-FW) | `config.cfg` | ✅ (cần `config="1"`) |
| vpcs (VPC11–54) | `config.txt` | ✅ |
| vtedge (vEdge1/2, vEdge65) | `config.cfg` | ⚠️ dán tay qua console an toàn nhất |
| linux (SDN_CONTROLLER, AccessTest, Access/Dist-SW) | `.sh` | ❌ chạy script thủ công trong VM |
| win / vtmgmt / vtsmart / vtbond | — | ❌ cấu hình qua GUI (xem dưới) |

**Các thiết bị cấu hình bằng tay (không có file):**
- **vManager (33) / vSmart (34) / vBond (35)**: khởi động vManager → vào GUI `https://10.9.0.10` (mặt LAN) hoặc `10.9.1.10` (mặt cloud). Setup cluster vBond→vSmart→vManager, cấp system-ip/site-id cho từng vEdge từ vManager (tính năng Zero-Touch/Manual). vSmart/vBond sau đó được cấu hình **từ xa qua vManager**.
- **Web-Server (22), Mail-Server (23), DHCP-Server (23/25), Syslog-Server (25), Win (36)**: đặt IP tĩnh qua Network Settings Windows:
  - Web-Server: 10.1.1.10/28, GW 10.1.1.1; Mail-Server: 10.1.1.11/28, GW 10.1.1.1
  - DHCP-Server: 10.1.90.10/24, GW 10.1.90.1 (cài role DHCP, tạo scope cho VLAN 10/20/30/40 theo mục 2.4 của md)
  - Syslog-Server: 10.1.90.11/24, GW 10.1.90.1
  - Win: 10.9.0.20/24, GW 10.9.0.2

## 5. Node Linux/OVS — cách chạy script

Các node dùng image `linux-ubuntu-ovs-16p` (Access-SW1–4, Dist-SW1/2, SDN_CONTROLLER, AccessTest):
- Boot node → console VNC (hoặc SSH từ EVE) → login root (password mặc định theo image).
- Copy nội dung file `.sh` tương ứng vào VM (hoặc chép qua SCP) rồi chạy:

  ```
  bash /root/<ten-script>.sh
  ```

- Để cấu hình tồn tại sau reboot: thêm script vào `/etc/rc.local` hoặc crontab `@reboot` (xem thêm `HuondanchitietController_OVS.md` trong repo).

> **Quan trọng**: AccessTest là thiết bị **test OpenFlow độc lập** (không nối vào mạng campus). Khi test: nối **trực tiếp** AccessTest **e1** ↔ SDN_CONTROLLER **e1** bằng dây trong EVE (control plane `192.168.100.0/24` theo hướng dẫn OVS: controller = 192.168.100.1, OVS = 192.168.100.2). SDN_CONTROLLER e0 = 10.1.100.2/24 vẫn là mặt quản lý campus (nối SwitchServerFarm e1/0).

## 6. Thứ tự khởi động lab khuyến nghị

1. Service Provider (Internet 26, MPLS 27) → Switch32/Switch61 + vManager/vSmart/vBond → các vEdge (28,6,29,42,30,40,31,41,65).
2. Site 100: Core-SW1/2 → FW → SwitchServerFarm/DMZ → Dist/Access → VPC.
3. Các chi nhánh: Brand-FW → SwitchBrand/SW → VPC.
4. Onboard vEdge qua vManager (đăng ký System-IP, site-id; kích hoạt tunnel IPsec).
5. Với SDN: chạy SDN_CONTROLLER script → AccessTest script → kiểm tra `ovs-vsctl show` thấy controller connected; ping VPC11 ↔ VPC12 (được controller cài flow).

## 7. Địa chỉ tóm tắt nhanh (theo bảng 2.2/2.3 của md)

| Thiết bị | IP chính | Mặt WAN |
|---|---|---|
| vEdge1-S100 / vEdge2-S100 | 10.200.100.1 / .2 | Internet 203.0.113.1 / .5 — MPLS 100.64.100.1 / .5 |
| vEdge1-S200 / vEdge2-S200 | 10.200.200.1 / .2 | Internet 203.0.113.9 — MPLS 100.64.200.1 |
| vEdge1-S300 / vEdge2-S300 | 10.200.300.1 / .2 | Internet 203.0.113.13 — MPLS 100.64.300.1 |
| vEdge1-S400 / vEdge2-S400 | 10.200.400.1 / .2 | Internet 203.0.113.17 — MPLS 100.64.400.1 |
| vEdge65 | 10.200.900.1 | Internet 203.0.113.245/30 |
| vManager/vSmart/vBond | 10.9.0.10 / .11 / .12 | Cloud 10.9.1.10 / .11 / .12 |
| SDN_CONTROLLER / AccessTest | 10.1.100.2 / 10.1.100.3 | — |
