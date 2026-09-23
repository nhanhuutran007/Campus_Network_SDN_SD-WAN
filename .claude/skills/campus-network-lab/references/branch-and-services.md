# Campus chi nhánh, DHCP-Server và dịch vụ

## Mục lục
- Mẫu chi nhánh (Sites 200/300/400) và quy trình 8 bước
- FW-ASAv HA và ASDM
- DHCP-Server node 72
- Web / Mail / Syslog / PC-Management
- Core-SW1/2 IOL: hai lỗi kinh điển
- Site 900: Switch32 và Switch61

## Mẫu chi nhánh (Sites 200/300/400)

Mỗi site: 1 **Brand-FW** (ASAv; gateway `.1` + `dhcpd` theo VLAN qua sub-interface) + 1 **SwitchBrand** (IOL, trunk lên FW + 2 SW) + 2 **SW phòng ban** (IOL, access cho 4 VPC) + 2 vEdge.

| Site | Brand-FW | SwitchBrand | SW (IP mgmt VLAN 99) | VLAN / VPC |
|---|---:|---:|---|---|
| 200 Cần Thơ | 37 | 63 (SVI `10.2.99.2`) | SW55 `.11`, SW56 `.12` | v60: VPC43,44 (SW55) · v70: VPC46, PC-YTe 47 (SW56) |
| 300 Đà Nẵng | 39 | 62 (SVI `10.3.99.2`) | SW58 `.11`, SW59 `.12` | v80: VPC50,54 (SW58) · v90: PC-TaiChinh 53, VPC48 (SW59) |
| 400 Nha Trang | 38 | 64 (SVI `10.4.99.2`) | SW60 `.11`, SW57 `.12` | v50: VPC51,45 (SW60) · v60: VPC49, PC-LuHanh 52 (SW57) |

Cổng chính xác của từng site khác nhau (S400: e0/0→FW; S200: e0/2→FW; …) — **lấy từ `config.cfg` và bảng 2.2.x, không hard-code**. SW phòng ban: `e0/0` trunk (vlanX + 99) lên SwitchBrand, `e0/1`,`e0/2` access vlanX cho 2 VPC.

**Nạp config**: Brand-FW (ASAv) tự nạp config nhúng — chỉ kiểm `show dhcpd state`. **IOL chi nhánh không tự nạp khi start bằng CLI** → dán tay qua console rồi `write memory`.

**8 bước** (mọi site):
1. Start 8 node của site; kiểm tra port console `33536 + id` LISTEN.
2. FW: `enable` → `show dhcpd state` ("Configured for DHCP SERVER" cho cả 2 VLAN) và `show interface ip brief` (sub-interface up/up).
3. Mỗi IOL: `enable` → `terminal length 0`.
4. `configure terminal` → dán: `vlan X` + `name`, các cổng trunk/access, `interface Vlan99` (IP + `no shutdown`). Nếu "Command rejected: trunk encapsulation Auto" → `switchport trunk encapsulation dot1q` **trước** `switchport mode trunk`.
5. `end` → `write memory`.
6. Verify `show vlan brief`, `show interfaces trunk`, `show running-config`.
7. VPC: `ip dhcp` rồi `ip` → kỳ vọng `10.<site>.<vlan>.10x`, GW `.1`.
8. Chưa nhận IP: đợi dhcpd của FW sẵn sàng, gõ lại `ip dhcp`, kiểm trunk `SwitchBrand↔FW` + sub-interface.

Kiểm theo lớp: access VLAN → trunk → sub-interface/DHCP của FW → route upstream; dừng ở lớp đầu tiên sai.

Tình trạng (theo bảng tiến độ 05/09): S400 đã verify DHCP; commit `4ad720f` ghi "Finalize branch campuses 200/300/400" — xác minh lại trạng thái live từng site trước khi báo hoàn tất.

## FW-ASAv HA và ASDM

- Active (node 1) = Primary, Standby (node 2) = Secondary; config **tự replicate** (hostname đồng bộ là bình thường). Failover LAN `10.1.255.0/29` (Gi0/5): khai **y hệt** trên 2 unit.
- OSPF: chỉ FW-Active chạy, neighbor Core-SW1 (inside `10.1.2.0/30`) và Core-SW2 (inside2 `10.1.2.4/30`); router-id FW-Active `10.1.3.5`.
- Quản trị: `Management0/0` (nameif management) VLAN 99 — Active `10.1.99.33`, Standby `.34` (`failover management-interface`), `http server enable`, `http 10.1.99.0 255.255.255.0 management`. **Bắt buộc một lần trên từng unit**, ở **config mode**: `crypto key generate rsa modulus 2048` (không replicate).
- ASDM 7.20(2) nhúng sẵn trong image (`show asdm image` = "not set" là bình thường). Từ PC-Management (`10.1.99.50`): `https://10.1.99.33/admin` → cài ASDM launcher (cần **JRE 8 32-bit**, ví dụ Zulu `win_i686` — Java cũ trên image làm launcher kẹt "Contacting the device…" với 0 packet ra mạng). Kiểm `show asdm sessions`.
- Đưa file vào PC Win7: HTTP server tạm trên host (`vnet6_<net>` + IP tạm), IE tải; dọn sau khi xong. Tải `dm-launcher.msi` bằng curl cần UA của IE + Referer + basic auth.

## DHCP-Server node 72

- Windows Server 2012 R2 (8192 MB), `10.1.90.10`, role DHCP bản địa, 4 scope Active: VLAN 10/20/30/40, pool `.100–.199`, GW `.1`. Core-SW1/2 relay `ip helper-address 10.1.90.10` (giaddr `10.1.10.2` Core-SW1 / `.3` Core-SW2).
- Điều kiện để VPC nhận IP: datapath SDN thông (xem `sdn-ryu-ovs.md`), DHCP-Server đã boot xong, relay lên. Lịch sử: 15/09/2026 VPC14+VPC19 nhận `10.1.10.100/.101`, DORA đủ, ping VLAN10 + gateway + liên VLAN OK. Chi nhánh dùng `dhcpd` trên Brand-FW (không dùng server này).
- Node 72 là `config="0"` — không wipe.

## Web / Mail / Syslog / PC-Management

- Web-Server node 22: `linux-ubuntu-18.04-server`, cấu hình tay (`configs/01-Site100-Campus/Web-Server/setup.sh`, đang sửa dở — xem git status). Trạng thái checkpoint: kiểm live trước khi hành động.
- Mail 13, Syslog 25, Win 36, PC-Management 73: Win7 (4096 MB). Syslog: Kiwi Syslog ở `10.1.90.11`; Core/Farm/FW-HA có `logging host`. Kiểm Syslog bằng UDP/514 đang lắng nghe, Windows Firewall, log đến thực tế — ping thành công chưa chứng minh gì.
- Thao tác GUI trên các node Windows do **người dùng** làm (gõ phím qua VNC không đáng tin).

## Core-SW1/2 IOL: hai lỗi kinh điển

1. Thiếu `vtp mode off` trước khối `vlan …` → switch IOL khác (Farm) có revision cao hơn quét sạch VLAN DB → `show vlan brief` rỗng, SVI down ("Vlans allowed and active in management domain: none").
2. Thiếu `switchport trunk encapsulation dot1q` trước `switchport mode trunk`.

Config nhúng của Core nạp được sau wipe+start (~100 s), nên có thể verify bằng prompt `Core-SW1>`.

## Site 900: Switch32 và Switch61

- **Switch32** (node 32, IOL L2 adventerprise): LAN controller `10.9.0.0/24`, giữ **static** CE-PE theo thiết kế; config nhúng không tự nạp khi wipe+start (ra initial-config dialog → gửi `no` ngay, có thể reload ~100 s), rồi dán tay.
- **Switch61** (node 61): cầu controller ↔ LAN thật (`e0/0` `no switchport` + `ip address dhcp`, `Vlan10` `10.9.1.1/24`, `ip routing`, `vtp mode off`). SVI Vlan `ip address dhcp` không nhận OFFER trên IOL — dùng routed port. Chi tiết truy cập GUI: `eve-ng-ops.md`.
