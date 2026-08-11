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
| Core-SW1 | 3 | **iol** (chuyển từ viosl2 ngày 11/08/2026) |
| Core-SW2 | 4 | **iol** (chuyển từ viosl2 ngày 11/08/2026) |
| Dist-SW1 | 5 | linux (OVS script) |
| vEdge2-S100 | 6 | vtedge |
| SwitchDMZ | 7 | iol |
| Dist-SW2 | 8 | linux (OVS script) |
| SDN_CONTROLLER | 9 | linux (OVS script) |
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
| DHCP-Server | 72 | winserver (cấu hình tay) |
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
| PC-Management | 73 | win (cấu hình tay) |

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
| iol (Core-SW1/2, SW55–61, SwitchBrand, SwitchDMZ, SwitchServerFarm) | `config.cfg` | ✅ (cần `config="1"`) |
| viosl2 / vios (Internet, MPLS — dự phòng) | `config.cfg` | ✅ (cần `config="1"`) |
| asav (FW-ASAv, Brand-FW) | `config.cfg` | ✅ (cần `config="1"`) |
| vpcs (VPC14–54) | `config.txt` | ✅ |
| vtedge (vEdge1/2, vEdge65) | `config.cfg` | ⚠️ dán tay qua console an toàn nhất |
| linux (SDN_CONTROLLER, Access/Dist-SW) | `.sh` | ❌ chạy script thủ công trong VM |
| win / vtmgmt / vtsmart / vtbond | — | ❌ cấu hình qua GUI (xem dưới) |

> **Core-SW1/2 (IOL từ 11/08/2026)**: image `i86bi_linux_l2-adventerprisek9-ms.SSA.high_iron_20190423.bin`, cổng `Ethernet0/x`/`Ethernet1/x`. Hai điểm bắt buộc trong config: (1) `vtp mode off` đặt trước khối `vlan ...` — nếu để VTP server mặc định (rev 0, domain rỗng), switch IOL khác (vd SwitchServerFarm) có rev cao hơn sẽ **quét sạch toàn bộ VLAN DB** khiến SVI down; (2) `switchport trunk encapsulation dot1q` trước mỗi `switchport mode trunk` (image l2 không nhận encapsulation Auto → "Command rejected").

> **VPC (PC ảo) mặc định xin DHCP**: `config.txt` chỉ chứa `ip dhcp` → PC tự xin IP từ scope tương ứng (campus: DHCP-Server 10.1.90.10 relay qua Core; chi nhánh: dhcpd trên Brand-FW; dải `.100–.199` theo mục 2.4 của md).

**Các thiết bị cấu hình bằng tay (không có file):**
- **vManager (33) / vSmart (34) / vBond (35)**: khởi động vManager → vào GUI `https://10.9.0.10` (mặt LAN) hoặc `10.9.1.10` (mặt cloud). Setup cluster vBond→vSmart→vManager, cấp system-ip/site-id cho từng vEdge từ vManager (tính năng Zero-Touch/Manual). vSmart/vBond sau đó được cấu hình **từ xa qua vManager**.
- **Web-Server (22), Mail-Server (13), DHCP-Server (72), Syslog-Server (25), Win (36), PC-Management (73)**: đặt IP tĩnh qua Network Settings Windows:
  - Web-Server: 10.1.1.10/28, GW 10.1.1.1; Mail-Server: 10.1.1.11/28, GW 10.1.1.1
  - DHCP-Server: 10.1.90.10/24, GW 10.1.90.1 (node 72 dùng image **winserver-S2012-R2-x64** — cài role **DHCP Server** bản địa, tạo scope cho VLAN 10/20/30/40 theo mục 2.4 của md; Core đã khai `ip helper-address 10.1.90.10` trên SVI nên relay tự hoạt động. **Trạng thái 08/2026: chưa cài role DHCP — cấp DHCP campus triển khai sau**)
  - Syslog-Server: 10.1.90.11/24, GW 10.1.90.1 (image `win-7-x86-IPCC-WSAlicensed` vẫn dùng được — nhận syslog là phần mềm ứng dụng như Kiwi Syslog/TFTPD64, không cần Windows Server. **Đã triển khai 12/08/2026**: dùng **Kiwi Syslog có sẵn trong image** (không cài Python), listen UDP 514 + rule firewall `syslog514`. Các thiết bị đã cấu hình `logging host 10.1.90.11`: Core-SW1/2, SwitchServerFarm (`logging host 10.1.90.11` — đã có trong config.cfg), FW-ASAv Active/Standby (`logging host inside 10.1.90.11` + `logging trap informational` + `logging enable`))
  - Win: 10.9.0.20/24, GW 10.9.0.2
  - **PC-Management: 10.1.99.50/24, GW 10.1.99.1** (nối SwitchServerFarm e2/0, access VLAN 99) — dùng để mở **ASDM** quản lý 2 FW: `https://10.1.99.33` (active) / `https://10.1.99.34` (standby), đăng nhập `admin`/`vnpro@2026` (cần Java 8)

> **FW-ASAv Active/Standby — ASDM management (11/08/2026)**: cả 2 FW cắm cổng **Management0/0** (NIC EVE id 0) vào SwitchServerFarm **e1/2 / e1/3** (access VLAN 99) với IP **10.1.99.33 / .34**; config đã khai `interface Management0/0` (nameif management), `failover management-interface management Management0/0` + `failover interface ip management 10.1.99.33 … standby 10.1.99.34` (active .33 / standby .34 tự hoán đổi), `http server enable` + `http 10.1.99.0 255.255.255.0 management`. **Bắt buộc 1 lần trên console cả 2 unit**: `crypto key generate rsa modulus 2048` (không replicate). ASDM 7.20(2) nhúng sẵn trong image (`show version` → Device Manager Version) nên không cần set `asdm image`.

## 5. Node Linux/OVS — cách chạy script

Các node dùng image `linux-ubuntu-ovs-16p` (Access-SW1–4, Dist-SW1/2, SDN_CONTROLLER):
- Boot node → console VNC (hoặc SSH từ EVE) → login root (password mặc định theo image).
- Copy nội dung file `.sh` tương ứng vào VM (hoặc chép qua SCP) rồi chạy:

  ```
  bash /root/<ten-script>.sh
  ```

- Để cấu hình tồn tại sau reboot: thêm script vào `/etc/rc.local` hoặc crontab `@reboot` (xem thêm `HuondanchitietController_OVS.md` trong repo).

> **SDN campus (từ 08/2026)**: SDN_CONTROLLER quản lý toàn bộ L2 campus qua OpenFlow 1.3 — Dist-SW1/2 (dpid 5, 8) + Access-SW1–4 (dpid 68, 66, 70, 69) với **control plane trên VLAN 99 MANAGEMENT** (dải 10.1.99.0/24, link uplink sẵn có — **không còn link riêng**, mạng cũ `10.1.100.0/24` + 6 link đã xóa 07/08/2026): SDN_CONTROLLER e0 = **10.1.99.10/24** → SwitchServerFarm e1/0 (access VLAN 99); mỗi switch giữ IP mgmt trong VLAN 99 (Dist 10.1.99.11/.12, Access .21–.24) và `set-controller br0 tcp:10.1.99.10:6653`. App Ryu: **`campus_switch_13.py`** (trong `configs/01-Site100-Campus/`) — chạy cùng `ryu.app.ofctl_rest` (REST port 8080). `BLOCK_PORTS` mặc định rỗng để mọi VPC dùng DHCP; mục **2.7** của `campus_network_sdn_sdwan.md` và cuối file app có hướng dẫn demo ACL/northbound. *(Node test cũ AccessTest + VPC11/12 đã xóa 04/08/2026.)*

### 5.1. Tự phục hồi Ryu/OVS sau stop/start

Không đưa nguyên các script khởi tạo `Dist-SW*.sh`/`Access-SW*.sh` có bước reset OVSDB vào `rc.local` hoặc `@reboot`. Dùng bộ persistence idempotent:

| File nguồn | Đích trong guest |
|---|---|
| `Campus-OVS-restore.sh` | `/root/Campus-OVS-restore.sh` trên 6 OVS |
| `systemd/ovs-nodes/<node>.env` | `/etc/default/campus-ovs` trên đúng OVS |
| `systemd/campus-ovs-restore.service` | `/etc/systemd/system/campus-ovs-restore.service` |
| `SDN_CONTROLLER-autostart.sh` | `/root/SDN_CONTROLLER-autostart.sh` trên node 9 |
| `Campus-Cloud-DHCP.sh` | `/root/Campus-Cloud-DHCP.sh` trên node 9 |
| `systemd/campus-ryu.service` | `/etc/systemd/system/campus-ryu.service` trên node 9 |
| `systemd/campus-cloud-dhcp.service` | `/etc/systemd/system/campus-cloud-dhcp.service` trên node 9 |

Sau khi copy đúng file và cấp quyền script:

```bash
systemctl daemon-reload
systemctl enable --now campus-ovs-restore.service   # trên OVS
systemctl enable --now campus-cloud-dhcp.service campus-ryu.service  # controller
```

Service OVS phục hồi bridge/port theo kiểu `--may-exist`, IP `br-mgmt`, DPID, controller, pruning VLAN 99 và hai flow bootstrap priority 50000. Unit được liên kết với `openvswitch-switch.service`, vì vậy restart daemon OVS cũng chạy lại script và khôi phục flow runtime. Service Ryu gán lại `10.1.99.10/24` trên `ens3` rồi giữ `ryu-manager` trong foreground. DHCP Cloud-NAT trên `ens6` chạy bằng service riêng để restart Ryu không sinh lease trùng. Stop/start thông thường tự phục hồi; wipe vẫn cần triển khai lại file.

## 6. Thứ tự khởi động lab khuyến nghị

1. Service Provider (Internet 26, MPLS 27) → Switch32/Switch61 + vManager/vSmart/vBond → các vEdge (28,6,29,42,30,40,31,41,65).
2. Site 100: Core-SW1/2 → FW → SwitchServerFarm/DMZ → Dist/Access → VPC.
3. Các chi nhánh: Brand-FW → SwitchBrand/SW → VPC.
4. Onboard vEdge qua vManager (đăng ký System-IP, site-id; kích hoạt tunnel IPsec).
5. Với SDN: chạy SDN_CONTROLLER script → script 6 switch campus (Dist/Access) → kiểm tra `ovs-vsctl show` thấy controller connected; `curl http://127.0.0.1:8080/stats/switches` → `[5, 8, 68, 66, 70, 69]`.

## 7. Địa chỉ tóm tắt nhanh (theo bảng 2.2/2.3 của md)

| Thiết bị | IP chính | Mặt WAN |
|---|---|---|
| vEdge1-S100 / vEdge2-S100 | 10.200.100.1 / .2 | Internet 203.0.113.1 / .5 — MPLS 100.64.100.1 / .5 |
| vEdge1-S200 / vEdge2-S200 | 10.200.200.1 / .2 | Internet 203.0.113.9 — MPLS 100.64.200.1 |
| vEdge1-S300 / vEdge2-S300 | 10.200.300.1 / .2 | Internet 203.0.113.13 — MPLS 100.64.300.1 |
| vEdge1-S400 / vEdge2-S400 | 10.200.400.1 / .2 | Internet 203.0.113.17 — MPLS 100.64.400.1 |
| vEdge65 | 10.200.900.1 | Internet 203.0.113.245/30 |
| vManager/vSmart/vBond | 10.9.0.10 / .11 / .12 | Cloud 10.9.1.10 / .11 / .12 |
| SDN_CONTROLLER | 10.1.99.10 (e0, mgmt/control VLAN 99); e3 = Cloud-NAT (pnet0, Internet) | — |
| Dist-SW1 / Dist-SW2 | mgmt/control 10.1.99.11 / .12 | controller 10.1.99.10:6653 |
| Access-SW1–4 | mgmt/control 10.1.99.21–.24 | controller 10.1.99.10:6653 |
