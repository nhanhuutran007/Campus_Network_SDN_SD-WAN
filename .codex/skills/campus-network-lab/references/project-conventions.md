# Quy ước dự án

## Mục lục

- Kiến trúc
- Nguồn dữ liệu
- Quy ước địa chỉ
- Quyết định thiết kế ổn định
- Node-id quan trọng
- Quy ước Git và trạng thái

## Kiến trúc

- Mô phỏng bốn campus trong một lab EVE-NG.
- Site 100 là campus chính tại Cần Thơ; site 200 là campus Cần Thơ; site 300 là Đà Nẵng; site 400 là Nha Trang; site 900 chứa SD-WAN controllers.
- SDN dùng Ryu và OpenFlow 1.3 để quản lý Dist-SW1/2 cùng Access-SW1–4 qua control plane trên VLAN 99 MANAGEMENT (10.1.99.0/24, dùng link uplink sẵn có — không có link riêng).
- SD-WAN dùng vManager, vSmart, vBond và hai vEdge tại mỗi campus; transport qua Internet và MPLS.

## Nguồn dữ liệu

| Artifact | Vai trò |
|---|---|
| `campus_network_sdn_sdwan.md` | Thiết kế chính, bảng IP/VLAN/link và topology Mermaid |
| `Campus Network SDN SD-WAN.unl` | Topology EVE-NG chính và startup config nhúng |
| `configs/` | Cấu hình nguồn theo thiết bị |
| `configs/README.md` | Ánh xạ thiết bị với node-id, upload và boot order |
| `HuondanchitietController_OVS.md` | Hướng dẫn Ryu/OVS của dự án |
| `HuongdancaiOVSchoUbuntu .txt` | Tài liệu cài OVS gốc; có thể chứa dải test lịch sử |

Ưu tiên artifact hiện tại trong working tree. Xem commit history khi cần giải thích lịch sử; không đưa HEAD hoặc “trạng thái hiện tại” vào skill vì nhanh lỗi thời.

## Quy ước địa chỉ

- Octet thứ hai biểu diễn campus: `1`, `2`, `3`, `4`; dùng `9` cho controller.
- VLAN dùng `/24`; gateway mặc định là `.1`; server thường dùng `.10`, `.11`.
- DHCP pool cho PC là `.100` đến `.199`.
- Point-to-point dùng `/30`; kiểm chứng đầu `.1`/`.2` trong bảng IP trước khi tạo config.
- Loopback OSPF theo mẫu `10.<site>.0.x/32`.
- OMP System-IP theo mẫu `10.200.<site>.x`; không dùng System-IP làm default gateway.
- Internet transport dùng `203.0.113.0/24`; MPLS dùng các subnet `/30` dưới `100.64.0.0/10` theo bảng thiết kế.
- SDN management/control plane dùng **VLAN 99 MANAGEMENT** (`10.1.99.0/24`) — không có link riêng (mạng cũ `10.1.100.0/24` + 6 link đã xóa khỏi lab 07/08/2026).
- SDN_CONTROLLER e0 dùng `10.1.99.10` về SwitchServerFarm e1/0 (access VLAN 99). Các switch dùng IP mgmt VLAN 99 (Dist-SW1/2 `.11`/`.12`, Access-SW1–4 `.21`–`.24`) và `set-controller tcp:10.1.99.10:6653`. Đối chiếu lại bảng 2.2.3 trước khi sửa interface mapping.
- Không khôi phục hai dải test cũ `10.1.101.0/24` và `192.168.100.0/24` nếu không có yêu cầu thiết kế mới.

## Quyết định thiết kế ổn định

- Hai mươi VPC phòng ban 14–21, 43, 44, 46, 47, 50, 54, 53, 48, 51, 45, 49 và 52 dùng file `config.txt` chỉ chứa `ip dhcp`; không gán lại IP tĩnh hàng loạt.
- DHCP-Server là node 72, Windows Server 2012 R2, RAM 8192 MB; Core-SW1/2 relay về `10.1.90.10`.
- DHCP tại branch do Brand-FW phục vụ bằng `dhcpd`.
- Web, Mail, Syslog và máy Win dùng image Win7 cùng ứng dụng bên thứ ba theo thiết kế hiện tại.
- AccessTest node 10 và VPC11/12 nodes 11/12 đã bị loại khỏi topology; không tạo lại nếu không có yêu cầu rõ ràng.
- Không khôi phục node DHCP cũ id 23 hoặc image Win7 cho DHCP-Server.
- Giữ các nhãn IP của thiết bị mạng trên canvas. Không khôi phục nhãn IP tĩnh của VPC phòng ban hoặc nhãn VPC11/12 đã xóa.
- Ryu quản lý Dist-SW1/2 và Access-SW1–4; giữ cấu hình VLAN `tag`/`trunks`, OpenFlow13, datapath-id và controller chung `tcp:10.1.99.10:6653`. Đặt `fail_mode=secure` và `stp_enable=false`: OVS STP từng chặn frame trước OpenFlow pipeline, làm controller không nhận packet-in.
- DPID hiện dùng node-id ở dạng hex có padding; DPID 5, 8, 68, 66, 70 và 69 lần lượt thuộc Dist-SW1/2, Access-SW1–4. App `campus_switch_13.py` học MAC theo VLAN và mở `ofctl_rest` trên 8080. Source hiện tại để `BLOCK_PORTS = {}`; khi bật demo ACL phải dùng đúng tên interface OVS như `ens6` và kiểm tra lại app thực tế trong guest.
- Không dùng lại mạng control riêng `10.1.100.0/24` hoặc các link control cũ. Kênh OpenFlow đi trên VLAN 99 MANAGEMENT qua SwitchServerFarm, Core và các uplink campus sẵn có; khi dùng flow bootstrap `NORMAL`, phải tạo đường VLAN 99 không vòng lặp theo [ryu-ovs-recovery.md](ryu-ovs-recovery.md).
- vEdge có thể cần paste config thủ công qua console sau lần boot đầu.
- Windows, SD-WAN controllers và Linux/OVS có các bước cấu hình thủ công; không giả định `config="1"` có thể thay thế mọi bước.
- Giữ `config="1"` cho đúng 51 node được khai trong validator; giữ `config="0"` cho Windows, vtmgmt/vtsmart/vtbond và Linux/OVS cần cấu hình tay.
- Node Windows thông thường dùng 4096 MB RAM; DHCP-Server node 72 dùng 8192 MB.
- Khi vEdge yêu cầu đặt mật khẩu boot đầu, nhận bí mật theo phiên và nhập giống nhau ở `Password:`/`Re-enter password:`. Tránh mật khẩu có ba ký tự lặp hoặc liên tiếp ASCII; không ghi giá trị bí mật vào file hay log.

## Node-id quan trọng

| Nhóm | Thiết bị và node-id |
|---|---|
| Core/security | FW-ASAv-Active 1; FW-ASAv-Standby 2; Core-SW1 3; Core-SW2 4; SwitchDMZ 7; SwitchServerFarm 24 |
| SDN | Dist-SW1 5; Dist-SW2 8; SDN_CONTROLLER 9; Access-SW1 68; Access-SW2 66; Access-SW3 70; Access-SW4 69 |
| Server | Mail 13; Web 22; Syslog 25; DHCP-Server 72 |
| Controllers | vManager 33; vSmart 34; vBond 35; Win 36 |
| vEdge | S100: 28/6; S200: 29/40; S300: 30/41; S400: 31/42; vEdge65: 65 |
| Transport | Internet 26; MPLS 27 |
| Branch firewall | S200 37; S400 38; S300 39 |
| Branch switching | SW55–60; SwitchBrand-S300 62; SwitchBrand-S200 63; SwitchBrand-S400 64 |

Đọc lại `configs/README.md` và `.unl` trước khi dùng node-id trong lệnh có tác động thật.

## Quy ước Git và trạng thái

- Chỉ commit hoặc push khi người dùng yêu cầu. Dùng commit message tiếng Anh ngắn gọn.
- Nhánh và remote lịch sử là `main` và `nhanhuutran007/Campus_Network_SDN_SD-WAN`; kiểm tra `git branch` và `git remote -v` trước khi tác động.
- Không tin câu mô tả “working tree sạch” hoặc một HEAD cố định trong ghi chú lịch sử. Luôn lấy trạng thái bằng `git status --short`, `git rev-parse HEAD` và kiểm tra artifact hiện tại.
- Các việc thường cần làm tay gồm cấu hình GUI vManager/vSmart/vBond, Windows services/apps, chạy script OVS và paste cấu hình vEdge. Xác định lại phần còn thiếu từ lab thật trước khi tuyên bố hoàn tất.
