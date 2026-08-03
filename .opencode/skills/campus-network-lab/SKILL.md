---
name: campus-network-lab
description: Dự án đồ án "Campus Network kết hợp SDN + SD-WAN" mô phỏng trên EVE-NG. Dùng khi làm việc với campus_network_sdn_sdwan.md, "Campus Network SDN SD-WAN.unl", thư mục configs/, các câu hỏi về cấu hình thiết bị EVE-NG (Core/FW/vEdge/OVS/VPC/DHCP). Chứa toàn bộ quy ước IP, bảng node-id, các quyết định thiết kế và trạng thái hiện tại của dự án.
---

# Dự án Campus Network SDN + SD-WAN (EVE-NG)

## Mô tả tổng quan

Đồ án mạng campus trường đại học (4 campus) kết hợp hai công nghệ trên một lab EVE-NG duy nhất:

- **SDN (OpenFlow)**: SDN_CONTROLLER (Ryu) quản lý các switch OVS (Access-SW1–4, Dist-SW1/2) + AccessTest (OVS test độc lập).
- **SD-WAN**: vManager/vSmart/vBond (site 900) + vEdge1/2 tại mỗi campus, transport qua Internet (203.0.113.0/24) và MPLS (100.64.0.0/30 nhỏ).

Các site: **100** = Campus chính (Cần Thơ), **200** = Cần Thơ, **300** = Đà Nẵng, **400** = Nha Trang, **900** = SD-WAN Controller.

## Ngôn ngữ làm việc

Người dùng (chủ đồ án) giao tiếp **tiếng Việt**. Trả lời và cập nhật tài liệu bằng tiếng Việt, giữ thuật ngữ kỹ thuật tiếng Anh. Người dùng gọi tôi là "bạn".

## Các file chính

| File | Vai trò |
|---|---|
| `campus_network_sdn_sdwan.md` | Tài liệu thiết kế chính (bảng IP 2.0–2.4, topo Mermaid, bảng liên kết 2.2.x, bảng VLAN/DHCP 2.4) |
| `Campus Network SDN SD-WAN.unl` | File topo EVE-NG — **file duy nhất được chỉnh sửa** (.unl.bak ĐÃ XÓA, không tạo lại) |
| `configs/` | Cấu hình từng thiết bị: `config.cfg` (IOS/ASAv/vEdge), `config.txt` (VPC), `.sh` (Linux/OVS) |
| `configs/README.md` | Bảng ánh xạ **thiết bị → node-id**, hướng dẫn upload EVE, thứ tự boot |
| `HuondanchitietController_OVS.md`, `HuongdancaiOVSchoUbuntu .txt` | Hướng dẫn Ryu/OVS (dải control plane 192.168.100.0/24) |

## Quy ước IP (đã thống nhất, không đổi nếu không được yêu cầu)

- Octet 2 = site: 1 = Campus chính, 2 = Cần Thơ, 3 = Đà Nẵng, 4 = Nha Trang, 9 = Controller.
- VLAN dùng /24; **gateway = `.1`** (VRRP VIP trên Core-SW1/2 hoặc sub-interface Brand-FW); server đặt `.10`, `.11`.
- Liên kết /30: FW↔Core, FW↔vEdge, vEdge↔SP; phía FW/vEdge gần WAN hơn = `.1`, đầu kia = `.2`.
- Loopback OSPF: `10.<site>.0.x/32`; System-IP OMP: `10.200.<site>.x` (không phải gateway).
- Mặt WAN: Internet `203.0.113.0/24`, MPLS `100.64.x.x/30`.
- **DHCP pool cho PC: `.100 – .199`**.
- Mạng SDN test: `10.1.101.0/24` (không có DHCP); management SDN `10.1.100.0/24` (SDN_CONTROLLER e0 = 10.1.100.2 ↔ SwitchServerFarm e1/0).
- Control plane OVS test: `192.168.100.0/24` (controller 192.168.100.1:6653, OVS 192.168.100.2).

## Các quyết định thiết kế QUAN TRỌNG (lịch sử làm việc)

1. **VPC phòng ban mặc định xin DHCP**: 20 file `config.txt` của VPC phòng ban (VPC14–21, 43, 44, 46, 47, 50, 54, 53, 48, 51, 45, 49, 52) chỉ chứa `ip dhcp`. Không đặt IP tĩnh.
2. **VPC11/12 BẮT BUỘC IP tĩnh** (10.1.101.11/.12, gw 10.1.101.1) — mạng test SDN không có DHCP server.
3. **DHCP-Server = node 72**, image `winserver-S2012-R2-x64` (Windows Server 2012 R2, RAM 8192MB) — cài **role DHCP bản địa**, tạo 4 scope (VLAN 10/20/30/40) theo bảng 2.4 md. Core-SW1/2 đã có `ip helper-address 10.1.90.10` trên SVI → relay tự hoạt động. **Node cũ id 23 (win-7) đã xóa** — không quay lại.
4. **Syslog/Web/Mail/Win giữ image `win-7-x86-IPCC-WSAlicensed`** (win client) — nhận syslog, web, mail là phần mềm ứng dụng thứ 3 (Kiwi Syslog, XAMPP…), chạy được trên Win7; Windows Server không có role syslog nên đổi image vô nghĩa.
5. **DHCP chi nhánh**: dhcpd trên Brand-FW (`dhcpd address ... vlanX`, `dhcpd enable vlanX`) đã khai trong config.cfg.
6. **AccessTest (node 10) là thiết bị test OpenFlow ĐỘC LẬP** — KHÔNG nối vào mạng campus, KHÔNG thêm link vào .unl. Khi test: nối trực tiếp **AccessTest e1 ↔ SDN_CONTROLLER e1** (dải 192.168.100.0/24).
7. **Nhãn text trên canvas .unl**: nhãn IP tĩnh của PC phòng ban đã xóa (textobject 147–166). Nhãn VPC11/12 (167/168) và nhãn IP thiết bị mạng GIỮ NGUYÊN.
8. **`config="1"`**: bật cho 53 node có file config trong cả .unl. Node win/vtmgmt/vtsmart/vtbond/Linux OVS giữ `config="0"` (cấu hình tay).
9. **vEdge (vtedge)**: EVE không đảm bảo nạp `config.cfg` tự động → dán tay qua console sau boot đầu.
10. **Deploy**: upload config vào `/opt/unetlab/labs/<user>/Campus Network SDN SD-WAN/<node-id>/` rồi **Wipe** node; VPC mới cần upload lại config.txt sau khi đổi DHCP.

## Bảng node-id quan trọng

FW-ASAv-Active 1, FW-ASAv-Standby 2, Core-SW1 3, Core-SW2 4, Dist-SW1 5, Dist-SW2 8, SwitchDMZ 7, SwitchServerFarm 24, SDN_CONTROLLER 9, AccessTest 10, VPC11 11, VPC12 12, Web 22, Mail 13, **DHCP-Server 72**, Syslog 25, Switch32 32, Switch61 61, vManager 33, vSmart 34, vBond 35, Win 36, vEdge1/2-S100 28/6, vEdge1/2-S200 29/40, vEdge1/2-S300 30/41, vEdge1/2-S400 31/42, vEdge65 65, Internet 26, MPLS 27, Brand-FW-S200 37, Brand-FW-S400 38, Brand-FW-S300 39, SW55–60, SwitchBrand-S300 62, SwitchBrand-S200 63, SwitchBrand-S400 64, VPC43–54, Access-SW2 66, Access-SW1 68, Access-SW4 69, Access-SW3 70.

## Quy trình làm việc chuẩn

1. Đọc `configs/README.md` để tra node-id; đọc `campus_network_sdn_sdwan.md` cho quy ước IP.
2. Sửa config → cập nhật đồng thời: md (nếu có thay đổi thiết kế) + configs/README.md + .unl (nếu thay đổi topo).
3. Sau khi sửa `.unl`: kiểm tra file còn **XML hợp lệ** (python xml.etree), không để lại network treo.
4. Giữ đồng bộ: số link giữa md (bảng 2.2.x) và .unl phải khớp.
5. Chỉ commit khi người dùng yêu cầu (thường là "up lên git"). Message commit tiếng Anh, ngắn gọn; nhánh `main`, remote `nhanhuutran007/Campus_Network_SDN_SD-WAN`.

## Trạng thái hiện tại (cập nhật sau mỗi phiên)

- HEAD: `31878c7` — VPC → DHCP, xóa nhãn IP PC trên canvas, DHCP-Server = win server 2012 R2, xóa .unl.bak.
- Working tree sạch (sau khi push). Cấu hình còn lại cần làm TAY trên lab: vManager/vSmart/vBond GUI, Windows servers (IP tĩnh + role DHCP trên node 72, syslog/web/mail app trên Win7), OVS scripts, vEdge paste config, cài Win7 image đã sửa.

## Lưu ý kỹ thuật lab

- Node 72 RAM 8GB, node Windows khác 4GB (image win-7 x86, ram 4096).
- Sau khi đổi config trên EVE phải Wipe node để nạp lại.
- VPC xin DHCP cần server đã boot xong; nếu chưa, gõ lại `ip dhcp` trong console vpcs.
