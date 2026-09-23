# Kiến trúc, quy ước và node-id

Nguồn đã đối chiếu ngày 2026-09-20: `Campus Network SDN SD-WAN.unl` (67 node, 100 network, 47 config nhúng — cập nhật 23/09/2026), `configs/README.md`, `campus_network_sdn_sdwan.md`. Khi nghi ngờ, chạy `python .claude/skills/campus-network-lab/scripts/unl_tool.py nodes`.

## Mục lục
- Kiến trúc tổng thể
- Thứ tự tin cậy của nguồn dữ liệu
- Quy ước địa chỉ, VLAN, ASN
- Node-id (đã kiểm chứng với .unl)
- Quyết định thiết kế đã chốt (KHÔNG làm lại)
- Image IOL: đừng đoán theo tên

## Kiến trúc tổng thể

Đồ án "Xây dựng mạng Campus Network sử dụng SDN và SD-WAN" (nhóm 2 người: Trần Hữu Nhân 52300235, Nguyễn Nhật Hào 52300198), mô phỏng trên EVE-NG.

| Site | Vai trò | Nội dung |
|---|---|---|
| 100 | Campus chính (Cần Thơ) | FW-ASAv HA, Core-SW1/2 (IOL), Dist-SW1/2 + Access-SW1–4 (OVS do Ryu điều khiển), Server Farm/DMZ, 2 vEdge |
| 200 / 300 / 400 | Chi nhánh Cần Thơ / Đà Nẵng / Nha Trang | Brand-FW (L3 + DHCP) + SwitchBrand + 2 SW phòng ban + 4 VPC + 2 vEdge |
| 900 | SD-WAN controller | vManager 33 / vSmart 34 / vBond 35, Switch32 (LAN controller), Switch61 (cầu ra LAN thật), vEdge65 |
| SP | Nhà cung cấp | Internet 26 (AS 64511), MPLS 27 (AS 64512) |

- **SDN**: Ryu (OpenFlow 1.3) điều khiển 6 OVS của Site 100. Control plane đi trên **VLAN 99 MANAGEMENT** (10.1.99.0/24) qua chính các uplink sẵn có — KHÔNG có mạng/link điều khiển riêng.
- **SD-WAN**: Viptela 20.10.1, 2 transport (Internet `biz-internet` + MPLS `mpls`), underlay là **BGP** (không còn OSPF).
- **Campus chính** 3 lớp Core/Dist/Access; **chi nhánh** dùng "Firewall-as-Core" (2 kiến trúc cùng tồn tại có chủ đích).

## Thứ tự tin cậy của nguồn dữ liệu

| Câu hỏi | Nguồn chuẩn (giảm dần) |
|---|---|
| Node/interface/link/network, config nhúng thực tế | `.unl` → live EVE |
| Cấu hình thiết bị | trạng thái live → `configs/` (chú ý drift, xem `unl_tool.py drift`) |
| Thiết kế, bảng IP/VLAN/link, lý do | `campus_network_sdn_sdwan.md` |
| Node-id ↔ tên, thứ tự boot | `configs/README.md` + `.unl` |
| Ảnh/nhãn trong `BAOCAO_DACNTT_LVT/prism-uploads/` | CHỈ minh họa — có nhãn IP cũ, không dùng làm nguồn cấu hình |

Không tin bảng node-id/trạng thái trong ghi chú cũ (`.opencode`, `.codex`) nếu mâu thuẫn với `.unl`: Codex từng ghi sai vEdge S200/S300/S400 là 29/40, 30/41, 31/42.

## Quy ước địa chỉ, VLAN, ASN

- Octet 2 = site: 1 Campus, 2 Cần Thơ, 3 Đà Nẵng, 4 Nha Trang, 9 Controller.
- VLAN `/24`, gateway `.1` (VRRP VIP trên Core hoặc sub-interface Brand-FW), server `.10/.11`. **DHCP pool `.100–.199`** cho PC.
- P2P `/30`: phía gần WAN (FW/vEdge) = `.1`. Loopback OSPF `10.<site>.0.x/32`.
- System-IP OMP: `10.200.<site>.x`, riêng site 300/400/900 rút octet thành `30/40/90` (octet >255 vô hiệu). System-IP không phải gateway.
- WAN: Internet `203.0.113.0/24` (Internet G0/0 nối pnet0 = **DHCP, cấm IP tĩnh**); MPLS `100.64.x.x/30` (S100 `.100.0/.100.4`, S200 `.200.0`, S300 `.30.0`, S400 `.40.0`, backbone `.254.0/30`).
- **Campus chính VLAN**: 10 Khoa CNTT (VPC14, 19), 20 Toán-TK (VPC20, 21), 30 Luật (VPC15, 16), 40 Hành chính (VPC17, PC-HanhChinh-S100 node 18), 90 Server Farm, 99 Management.
- **VLAN 99 (10.1.99.0/24)**: `.1/.2` Core (SVI), `.10` SDN_CONTROLLER, `.11/.12` Dist-SW1/2, `.21–.24` Access-SW1–4, `.31` DMZ, `.32` Farm, `.33/.34` FW-Active/Standby (ASDM), `.50` PC-Management.
- Server Farm `10.1.90.0/24`: DHCP-Server `.10`, Syslog `.11`. Core SVI có `ip helper-address 10.1.90.10`.
- Chi nhánh: S200 v60 Nông nghiệp + v70 Y tế; S300 v80 Du lịch + v90 Tài chính; S400 v50 Thủy sản + v60 Lữ hành; mỗi site thêm v99.
- FW failover LAN `10.1.255.0/29`: lệnh `failover interface ip failover 10.1.255.1 255.255.255.248 standby 10.1.255.2` khai **giống hệt** trên cả 2 unit (ASA tự gán theo vai trò). Khai kiểu secondary → cả hai đều lấy `.1`, không negotiate.
- ASN: Internet 64511, MPLS 64512; site 100/200/300/400 = 65000/65010/65020/65030 (eBGP CE-PE). Site 900 dùng **static CE-PE** (Switch32).
- Dải test cũ `10.1.100.0/24`, `10.1.101.0/24`, `192.168.100.0/24` đã bỏ — không khôi phục.

## Node-id (khớp `.unl` ngày 2026-09-20)

| Nhóm | Node-id |
|---|---|
| Firewall HA | FW-ASAv-Active 1, FW-ASAv-Standby 2 |
| Core / Farm / DMZ | Core-SW1 3, Core-SW2 4 (IOL), SwitchDMZ 7, SwitchServerFarm 24 |
| SDN (OVS/Ryu) | Dist-SW1 5, Dist-SW2 8, SDN_CONTROLLER 9, **Access-SW1 68, Access-SW2 66, Access-SW3 70, Access-SW4 69** |
| Server / quản trị | Mail 13, Web 22, Syslog 25, Win 36, DHCP-Server 72, PC-Management 73 |
| SD-WAN controller | vManager 33, vSmart 34, vBond 35 |
| vEdge Site 100 | vEdge1 = **28**, vEdge2 = **6** |
| vEdge Site 200 | vEdge1 29, vEdge2 **42** |
| vEdge Site 300 | vEdge1 30, vEdge2 **40** |
| vEdge Site 400 | vEdge1 31, vEdge2 **41** |
| Site 900 | Switch32 (32), Switch61 (61), vEdge65 (65) |
| SP | Internet 26, MPLS 27 |
| Brand-FW | S200 **37**, S400 **38**, S300 **39** |
| SwitchBrand | S300 62, S200 63, S400 64 |
| SW phòng ban | S200: 55, 56; S300: 58, 59; S400: 57, 60 |
| VPC | Site100: 14–17, 19–21; S200: 43, 44, 46; S300: 48, 50, 54; S400: 45, 49, 51 |
| PC Linux (Ubuntu 18.04 GNOME, Firefox/Thunderbird, DHCP, VNC `eve`) | S100 v40: **18** PC-HanhChinh · S200 v70: **47** PC-YTe · S300 v90: **53** PC-TaiChinh · S400 v60: **52** PC-LuHanh; `firstmac` 00:06:00:00:<id>:00 |

Tên node trong `.unl` trùng nhau (nhiều `vEdge1`, `SW`, `VPC`) — luôn phân biệt bằng **id**. Node 10, 11, 12, 23 đã xoá vĩnh viễn.

DPID OVS = node-id dạng hex 16 chữ số: Dist-SW1 `…05`, Dist-SW2 `…08`, Access-SW1 `…44`, Access-SW2 `…42`, Access-SW3 `…46`, Access-SW4 `…45`. Các tài liệu cũ đôi khi viết "dpid 68" theo thập phân — cùng một thiết bị.

## Quyết định thiết kế đã chốt (KHÔNG làm lại nếu không được yêu cầu)

1. 20 VPC phòng ban chỉ có `ip dhcp` trong `config.txt`, không gán IP tĩnh hàng loạt.
2. AccessTest (node 10), VPC11/12 đã xoá 04/08/2026; node DHCP cũ id 23 (Win7) đã xoá.
3. **DHCP-Server = node 72**, Windows Server 2012 R2, RAM 8192, role DHCP bản địa, 4 scope VLAN 10/20/30/40. Mail/Syslog/Win/PC-Management giữ image Win7 (Kiwi Syslog, XAMPP… là phần mềm thứ ba).
4. **Chi nhánh "Firewall-as-Core"**: Brand-FW làm gateway `.1` + `dhcpd`; SwitchBrand và SW là L2 thuần. Đã cân nhắc thay SwitchBrand bằng router IOS và **từ chối** (IOL không có `ip dhcp pool`, thêm hop/điểm lỗi, vEdge đã là router WAN). Không đổi `.unl`.
5. **Core-SW1/2 = IOL** (thay viosl2 vì CPU-hog + không nạp config ổn định). Bắt buộc `vtp mode off` trước khối `vlan`, và `switchport trunk encapsulation dot1q` trước `switchport mode trunk`. Cổng Core↔FW: Core-SW1 `E0/3`↔FW-Standby Gi0/1, `E1/0`↔FW-Active Gi0/0; Core-SW2 `E0/3`↔FW-Active Gi0/1, `E1/0`↔FW-Standby Gi0/0.
6. **FW HA** chạy: Active = Primary, Standby = Secondary, config tự replicate; chỉ FW-Active chạy OSPF với Core. ASDM qua Management0/0 trong VLAN 99 (`.33/.34`), cần `crypto key generate rsa modulus 2048` ở config-mode **trên từng unit**, và JRE 8 32-bit trên PC Win7.
7. **Underlay SP = BGP** (quyết định 15/08/2026, "thực tế & chuyên nghiệp"). `default-originate` phải đặt **trong address-family** (IOS).
8. **Ryu quản lý toàn bộ L2 campus**: giữ `tag=/trunks=` của OVS, `protocols=OpenFlow13`, `fail_mode=secure`, `stp_enable=false` (STP của OVS chặn frame trước pipeline), controller `tcp:10.1.99.10:6653`.
9. `config="1"` đúng **47 node** (danh sách trong `unl_tool.py`); Windows/vtmgmt/vtsmart/vtbond/Linux-OVS giữ `config="0"` (cấu hình tay). Không tái tạo `.unl.bak`.
10. Nhãn IP thiết bị mạng trên canvas giữ nguyên; nhãn IP tĩnh của VPC đã xoá — không khôi phục.

## Image IOL: đừng đoán theo tên

- `i86bi_linux_l2-adventerprisek9-ms.SSA.high_iron_20190423.bin` (Core, Switch32, Switch61, SW55–60): L3 switch đầy đủ — `switchport`, SVI, `ip routing`, `no switchport` (routed port), VRRP, OSPF.
- `i86bi_linux_l2-ipbasek9-ms.high_iron_aug9_2017b.bin` (SwitchDMZ, SwitchServerFarm, SwitchBrand): L2/ipbase.
- `i86bi_LinuxL3-AdvEnterpriseK9-M…` / `L3-ADVENTERPRISEK9-M-*`: **router IOS thuần** — không có `vlan`, `interface Vlan`, `switchport`.
- Chỉ `viosl2` thiếu L3 forwarding. Xác minh bằng `show version` và thử lệnh (`?`) trước khi đổi image.
- Cổng IOL: id EVE = `port*16 + module` (module 0 = `Ethernet0/x`, module 1 = `Ethernet1/x`), ví dụ id 48 = E0/3, id 1 = E1/0. Luôn lấy mapping từ `.unl`, đừng suy từ node khác.
