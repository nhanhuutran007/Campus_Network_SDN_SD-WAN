---
name: campus-network-lab
description: Dự án đồ án "Campus Network kết hợp SDN + SD-WAN" mô phỏng trên EVE-NG. Dùng khi làm việc với campus_network_sdn_sdwan.md, "Campus Network SDN SD-WAN.unl", thư mục configs/, các câu hỏi về cấu hình thiết bị EVE-NG (Core/FW/vEdge/OVS/VPC/DHCP). Chứa toàn bộ quy ước IP, bảng node-id, các quyết định thiết kế và trạng thái hiện tại của dự án.
---

# Dự án Campus Network SDN + SD-WAN (EVE-NG)

## Mô tả tổng quan

Đồ án mạng campus trường đại học (4 campus) kết hợp hai công nghệ trên một lab EVE-NG duy nhất:

- **SDN (OpenFlow)**: SDN_CONTROLLER (Ryu) quản lý các switch OVS (Access-SW1–4, Dist-SW1/2) qua OpenFlow 1.3, control plane trên **VLAN 99 MANAGEMENT** (10.1.99.0/24, dùng link uplink sẵn có — không có link riêng).
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
| `HuondanchitietController_OVS.md`, `HuongdancaiOVSchoUbuntu .txt` | Hướng dẫn Ryu/OVS (dải test cũ 192.168.100.0/24 — AccessTest đã xóa, chỉ giữ làm tài liệu gốc) |

## Quy ước IP (đã thống nhất, không đổi nếu không được yêu cầu)

- Octet 2 = site: 1 = Campus chính, 2 = Cần Thơ, 3 = Đà Nẵng, 4 = Nha Trang, 9 = Controller.
- VLAN dùng /24; **gateway = `.1`** (VRRP VIP trên Core-SW1/2 hoặc sub-interface Brand-FW); server đặt `.10`, `.11`.
- Liên kết /30: FW↔Core, FW↔vEdge, vEdge↔SP; phía FW/vEdge gần WAN hơn = `.1`, đầu kia = `.2`.
- Loopback OSPF: `10.<site>.0.x/32`; System-IP OMP: `10.200.<site>.x` (không phải gateway).
- Mặt WAN: Internet `203.0.113.0/24`, MPLS `100.64.x.x/30`.
- **DHCP pool cho PC: `.100 – .199`**.
- Management/control plane SDN trên **VLAN 99**: SDN_CONTROLLER **e0 = 10.1.99.10/24** ↔ SwitchServerFarm e1/0 (access VLAN 99); các switch dùng IP mgmt VLAN 99 (Dist .11/.12, Access .21–.24) + `set-controller tcp:10.1.99.10:6653`. **SDN_CONTROLLER e3 = Cloud-NAT (pnet0)** — Internet từ host EVE cho cài Ryu/pip, không phải control plane.
- Dải test cũ `10.1.101.0/24` (AccessTest + VPC11/12) và `192.168.100.0/24` (test tay OVS) đã bỏ khi xóa AccessTest 04/08/2026.

## Các quyết định thiết kế QUAN TRỌNG (lịch sử làm việc)

1. **VPC phòng ban mặc định xin DHCP**: 20 file `config.txt` của VPC phòng ban (VPC14–21, 43, 44, 46, 47, 50, 54, 53, 48, 51, 45, 49, 52) chỉ chứa `ip dhcp`. Không đặt IP tĩnh.
2. **VPC11/12 từng BẮT BUỘC IP tĩnh** (10.1.101.11/.12, gw 10.1.101.1) — mạng test SDN không có DHCP server. **ĐÃ XÓA cùng AccessTest 04/08/2026** (không còn node 10/11/12 trong lab).
3. **DHCP-Server = node 72**, image `winserver-S2012-R2-x64` (Windows Server 2012 R2, RAM 8192MB) — cài **role DHCP bản địa**, tạo 4 scope (VLAN 10/20/30/40) theo bảng 2.4 md. Core-SW1/2 đã có `ip helper-address 10.1.90.10` trên SVI → relay tự hoạt động. **Node cũ id 23 (win-7) đã xóa** — không quay lại.
4. **Syslog/Web/Mail/Win giữ image `win-7-x86-IPCC-WSAlicensed`** (win client) — nhận syslog, web, mail là phần mềm ứng dụng thứ 3 (Kiwi Syslog, XAMPP…), chạy được trên Win7; Windows Server không có role syslog nên đổi image vô nghĩa.
5. **DHCP chi nhánh**: dhcpd trên Brand-FW (`dhcpd address ... vlanX`, `dhcpd enable vlanX`) đã khai trong config.cfg.
6. **AccessTest (node 10) từng là thiết bị test OpenFlow ĐỘC LẬP** (không nối mạng campus, nối tay e1 ↔ SDN_CONTROLLER e3 dải 192.168.100.0/24). **ĐÃ XÓA 04/08/2026** cùng VPC11/12 — không tạo lại.
7. **Nhãn text trên canvas .unl**: nhãn IP tĩnh của PC phòng ban đã xóa (textobject 147–166). Nhãn VPC11/12 (167/168) đã xóa cùng AccessTest (04/08/2026); nhãn IP thiết bị mạng GIỮ NGUYÊN.
8. **`config="1"`**: bật cho 51 node có file config trong cả .unl (sau khi xóa AccessTest 10 + VPC11/12). Node win/vtmgmt/vtsmart/vtbond/Linux OVS giữ `config="0"` (cấu hình tay).
9. **vEdge (vtedge)**: EVE không đảm bảo nạp `config.cfg` tự động → dán tay qua console sau boot đầu.
10. **Deploy**: upload config vào `/opt/unetlab/labs/<user>/Campus Network SDN SD-WAN/<node-id>/` rồi **Wipe** node; VPC mới cần upload lại config.txt sau khi đổi DHCP.
11. **SDN quản lý toàn bộ L2 campus (08/2026)**: Ryu (`campus_switch_13.py` + `ofctl_rest`) quản lý Dist-SW1/2 (dpid 5, 8) + Access-SW1–4 (dpid 68, 66, 70, 69) qua **control plane trên VLAN 99 MANAGEMENT** — **KHÔNG còn link riêng** (mạng 10.1.100.0/24 + 6 link cũ #40–45 đã xóa khỏi .unl 07/08/2026): SDN_CONTROLLER **e0 = 10.1.99.10/24** → SwitchServerFarm e1/0 (access VLAN 99); kênh OpenFlow đi trên VLAN 99 qua các link uplink sẵn có (Dist/Access có IP mgmt .11/.12/.21–.24 trong VLAN 99). Mỗi switch `set-controller br0 tcp:10.1.99.10:6653`. Script `.sh` các switch: `protocols=OpenFlow13`, `other_config:datapath-id=0…<node-id hex>`, `set-controller tcp:10.1.99.10:6653`, `fail_mode=secure` (chỉ forward theo flow Ryu; app phải có table-miss priority 0), `stp_enable=false` (OVS STP chặn frame trước pipeline), `br-mgmt` (VLAN 99) + IP mgmt. App `campus_switch_13.py`: L2 học MAC **theo VLAN** (dùng tag=/trunks= của OVS — KHÔNG xóa các dòng đó khỏi script), ACL proactive (`BLOCK_PORTS` mặc định chặn VPC14 = (68,'ens6')), flood đúng VLAN. Node test cũ AccessTest + VPC11/12 **đã xóa 04/08/2026**.

## Bảng node-id quan trọng

FW-ASAv-Active 1, FW-ASAv-Standby 2, Core-SW1 3, Core-SW2 4, Dist-SW1 5, Dist-SW2 8, SwitchDMZ 7, SwitchServerFarm 24, SDN_CONTROLLER 9, Web 22, Mail 13, **DHCP-Server 72**, Syslog 25, Switch32 32, Switch61 61, vManager 33, vSmart 34, vBond 35, Win 36, vEdge1/2-S100 28/6, vEdge1/2-S200 29/40, vEdge1/2-S300 30/41, vEdge1/2-S400 31/42, vEdge65 65, Internet 26, MPLS 27, Brand-FW-S200 37, Brand-FW-S400 38, Brand-FW-S300 39, SW55–60, SwitchBrand-S300 62, SwitchBrand-S200 63, SwitchBrand-S400 64, VPC43–54, Access-SW2 66, Access-SW1 68, Access-SW4 69, Access-SW3 70. *(AccessTest 10, VPC11 11, VPC12 12 — ĐÃ XÓA 04/08/2026.)*

## RECIPE — Cấu hình campus chi nhánh (Sites 200/300/400) — tái sử dụng

Khuôn mẫu **giống hệt** cho 3 chi nhánh: 1 **Brand-FW (asav)** — DHCP server + router-on-a-stick qua subinterface; 1 **SwitchBrand (iol)** — trunk lên FW + 2 switch phòng ban; 2 **switch phòng ban (iol)** — access cho 4 VPC (`config.txt` = `ip dhcp`).

**Nguyên tắc nạp config:**
- **Brand-FW**: config nhúng `.unl` được ASAv tự nạp (dhcpd sẵn sàng) — chỉ cần verify `show dhcpd state` = "Configured for DHCP SERVER".
- **IOL (SwitchBrand/SW)** — **KHÔNG tự nạp config nhúng** khi start qua CLI (`unl_wrapper`) → **bắt buộc dán tay qua console** (mục Cách B dưới). Sau khi dán: `write memory`.

**Cổng console telnet:** `32768 + 128*6 + <node-id>` = `33536 + <node-id>`.

| Node (site) | FW (asav) | SwitchBrand (iol) | Switch PP (iol) | VLAN/SVI |
|---|---|---|---|---|
| **S200 Cần Thơ** (octet2) | 37 | 63 (SVI .2) | SW55 `10.2.99.11`, SW56 `10.2.99.12` | v60 NONG-NGHIEP, v70 Y-TE, v99 (10.2.99.0/24) |
| **S300 Đà Nẵng** (octet3) | 39 | 62 (SVI .2) | SW58 `10.3.99.11`, SW59 `10.3.99.12` | v80 DU-LICH, v90 TAI-CHINH, v99 |
| **S400 Nha Trang** (octet4) | 38 | 64 (SVI 10.4.99.2) | SW60 `10.4.99.11`, SW57 `10.4.99.12` | v50 THUY-SAN, v60 LU-HANH |

**VLAN/DHCP theo site (đều dhcpd trên Brand-FW, pool `.100–.199`, GW `.1`):**
- S200: `vlan60`=NONG-NGHIEP (10.2.60.1) + `vlan70`=Y-TE (10.2.70.1) → dhcpd 10.2.60.100–199 / 10.2.70.100–199.
- S300: `vlan80`=DU-LICH (10.3.80.1) + `vlan90`=TAI-CHINH (10.3.90.1) → dhcpd 10.3.80.100–199 / 10.3.90.100–199.
- S400: `vlan50`=THUY-SAN (10.4.50.1) + `vlan60`=LU-HANH (10.4.60.1) → dhcpd 10.4.50.100–199 / 10.4.60.100–199.

**Ánh xạ cổng IOL (chuẩn):**
- SwitchBrand `e0/0` (hoặc e0/2) → FW `Gi0/2`/`Gi0/0` trunk cả 2 vlan nghiệp vụ + 99 (tùy site: S400 dùng e0/0→FW, e0/1→SWvlan1, e0/2→SWvlan2; S200 dùng e0/0→SW55, e0/1→SW56, e0/2→FW; S300 dùng e0/0→FW, e0/1→SW58, e0/2→SW59 — theo từng config.cfg). `trunk allowed` từng cặp vlan+99. SVI Vlan99 `10.<site>.99.2`.
- Switch phòng ban `e0/0` → SwitchBrand (trunk vlanX+99); `e0/1`,`e0/2` → 2 VPC (access vlanX). SVI `10.<site>.99.11` / `.12`.

**VPC → VLAN (để test DHCP):** S200: SW55 vlan60 = VPC43,44; SW56 vlan70 = VPC46,47. S300: SW58 vlan80 = VPC50,54; SW59 vlan90 = VPC53,48. S400: SW60 vlan50 = VPC51,45; SW57 vlan60 = VPC49,52.

**Quy trình 8 bước (áp dụng cho bất kỳ site nào):**
1. Start 8 node của site (FW + SwitchBrand + 2 SW + 4 VPC) từ GUI; kiểm tra cổng console `33536 + <node-id>` LISTEN (`ss -tlnp` / `Get-NetTCPConnection`).
2. Telnet FW → `enable` → `show dhcpd state`; thấy "Configured for DHCP SERVER" cho cả 2 vlan → OK (không cần sửa). Interface: `show interface ip brief` (sub-interface .site lên `up/up`).
3. Với mỗi IOL: telnet → `enable` → `terminal length 0` (tránh `--More--`).
4. `configure terminal` → dán đủ: `vlan X/ name` (3 vlan), từng `interface Ethernet0/N` với `switchport mode trunk` (+ `switchport trunk allowed vlan ...`), access port, `interface Vlan99/ ip address/p no-shutdown`. **Nếu gặp "Command rejected: trunk encapsulation Auto"** (thường gặp trên SwitchBrand image ipbase) → gõ `switchport trunk encapsulation dot1q` TRƯỚC `switchport mode trunk`.
5. `end` → `write memory` → ghi lại size (vd S400 SwitchBrand 813B).
6. Verify: `show vlan brief` (thấy vlanX active + cổng access) và `show running-config` đủ.
7. VPC: từ console gõ `ip dhcp` rồi `ip` — mong đợi mỗi PC nhận `10.<site>.<vlan1>.10x` / `vlan2.10x`, GW `.1`.
8. Nếu PC chưa nhận IP: đợi FW dhcpd sẵn sàng, reboot lại VPC hoặc gõ lại `ip dhcp`; kiểm tra trunk `e0/0↔Gi0/2` và sub-interface up.

## Quy trình làm việc chuẩn

1. Đọc `configs/README.md` để tra node-id; đọc `campus_network_sdn_sdwan.md` cho quy ước IP.
2. Sửa config → cập nhật đồng thời: md (nếu có thay đổi thiết kế) + configs/README.md + .unl (nếu thay đổi topo).
3. Sau khi sửa `.unl`: kiểm tra file còn **XML hợp lệ** (python xml.etree), không để lại network treo, **đếm lại `config="1"` phải = 51** và đúng 51 node (1,2,3,4,26,27,28,29,30,31,32,14,15,16,17,18,19,20,21,37,38,39,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,6,7,24,40,41,42,65).
4. Giữ đồng bộ: số link giữa md (bảng 2.2.x) và .unl phải khớp.
5. Chỉ commit khi người dùng yêu cầu (thường là "up lên git"). Message commit tiếng Anh, ngắn gọn; nhánh `main`, remote `nhanhuutran007/Campus_Network_SDN_SD-WAN`.

## Cập nhật `.unl` lên EVE — CƠ CHẾ CONFIG NHÚNG (QUAN TRỌNG, HEAD `c4a8e70`)

**Phát hiện quan trọng (đã debug source mã EVE):** khi start node, EVE **CHỈ nạp config từ phần NHÚNG `<configs><config id="N">base64</config>` bên trong `.unl`** (`__lab.php:211–217` ép `config="0"` nếu thiếu phần nhúng; `cli.php:841–843` chỉ dump config khi `config=="1"` VÀ `config_data != ''`). File `config.cfg`/`config.txt` trong thư mục node trên server **KHÔNG được EVE đọc khi start** (chỉ có tác dụng khi user paste tay). `config_script`: iol/vpcs = embedded, viosl2 = `config_viosl2.py`, asav = `config_asav.py`, vtedge = `config_vtedge.py` — tất cả lấy config từ phần nhúng.

**GUI EVE ghi đè `.unl` khi mở/save lab**: reset `config="1"` → 0 và làm mất config nhúng (đã từng xảy ra — nguyên nhân Core-SW1 hostname "Switch" dù đã upload config.cfg).

Quy tắc:

- **Thiết kế config**: config phải được **nhúng base64 vào `.unl`** trong repo (không chỉ đặt file trong configs/). Khi thêm/sửa config thiết bị: cập nhật cả `configs/<id>/...` VÀ phần `<configs>` nhúng trong `.unl` (script hoặc python xml.etree để build). Verify: đếm node `config="1"` = 51 và trùng khớp id với `<config id=`.
- **Repo → EVE** (sửa .unl trong repo): commit/push xong → **SCP ghi đè DUY NHẤT file `.unl`** lên `/opt/unetlab/labs/TranHuuNhan-PKT/Campus Network SDN SD-WAN.unl`. Backup trước (`cp /opt/unetlab/labs/.../*.unl /tmp/unl.backup`). Sau đó **Wipe + Start node qua CLI** (GUI reload có thể đè cờ):
  `/opt/unetlab/wrappers/unl_wrapper -a wipe -T 6 -F "<path>.unl"` rồi `-a start -T 6 -F ...` (thêm `-D <node>` để chỉ 1 node; wipe toàn lab sẽ xóa cả lab state).
- **EVE GUI → repo** (user sửa tay): chỉ Export `.unl` → ghi đè repo → **kiểm tra trước khi push**: 51 node `config="1"` + 51 config nhúng (GUI export sẽ MẤT phần nhúng → phải nhúng lại!), XML hợp lệ, node-id/network-id không đổi.
- **CẤM tuyệt đối**: chu kỳ Delete lab → Import lại — mất config nhúng + reset cờ `config="1"` (từng xảy ra, `5222ac6` là bản sửa).
- **Xác minh sau boot**: console telnet mỗi node trên port động — tìm bằng `ss -tlnp | grep qemu` (port của node X = process qemu pid của node đó), kết nối TCP thấy prompt như `Core-SW1>` là config OK. Server: `/opt/unetlab/tmp/6/<lab-uuid>/<node-id>/startup-config` là config thực tế viosl2 nạp.
- SSH EVE host 1 (chính, trên server): `10.215.28.26`, user `root` (pass do người dùng cấp từng phiên, không lưu vào file). Dùng paramiko; verify md5 sau upload.
- Nếu thêm node MỚI: nhúng config mới + bật `config="1"` trong .unl.

## EVE host 2 (DỰ PHÒNG, USB boot trên VMware) — ĐỒNG BỘ host1 ↔ host2

**Thông tin host 2 (10/08/2026):** SSH `root@10.0.239.137`, pass **`eve`** (mặc định EVE-NG, đổi khi nào user yêu cầu). EVE-NG **6.7.5** (mới hơn host 1 — kernel 4.20.17). Lab đặt tại `/opt/unetlab/labs/TranHuuNhan-PKT/` (giống host 1). *Lưu ý: skill cũ ghi IP 192.168.2.18 NHƯNG user xác nhận 10/08/2026 host 2 đang dùng IP 10.0.239.137 (pnet0 = 10.0.239.137/16, gateway 10.0.0.1) — luôn thử cả 2 IP nếu không kết nối được.*

**Mục đích:** EVE dự phòng chạy trên laptop (VMware + USB boot) — khi host 1 trên server gặp sự cố, mở lab trên host 2 là chạy được.

**Image trên host 2 (đã đầy đủ 10/08/2026 — user tự tải lên):** asav-9-20-2-2, asa-915, viosl2 (high_iron_20180619), vios (157-3.M3), vtedge/vtmgmt/vtsmart/vtbond-20.10.1, win-7-x86-IPCC-WSAlicensed, **linux-ubuntu-ovs-16p (3.0G, size khớp host 1)**, **winserver-S2012-R2-x64 (4.5G, size khớp host 1)**, IOL đủ + iourc license, c8000v, fmc7/ftd7.

**Host 1 → host 2 KHÔNG reach trực tiếp** (10.215.x ≠ 192.168.2.x, test `/dev/tcp/<host2-ip>/22` = NOT-REACHABLE) → **mọi đồng bộ phải qua PC làm trung gian** (paramiko SFTP: get từ host 1 → put lên host 2).

**QUY TRÌNH ĐỒNG BỘ topo + config (host 1 → host 2)** — đã thực hiện lần đầu 09/08/2026:
1. **Download từ host 1** (paramiko sftp, script python): `/opt/unetlab/labs/TranHuuNhan-PKT/Campus Network SDN SD-WAN.unl` + toàn bộ thư mục `Campus Network SDN SD-WAN/` (config.cfg/config.txt từng node) → thư mục tạm PC (`C:\Users\<user>\AppData\Local\Temp\opencode\evebackup\lab`).
2. **Verify bản local** (python xml.etree): XML hợp lệ, **66 node, `config="1"` = 51, config id = 51, networks = 97** (đếm bằng `re.findall` vì GUI hiển thị sơ sài).
3. **Upload lên host 2**: `mkdir -p /opt/unetlab/labs/TranHuuNhan-PKT/`, sftp put .unl + thư mục node configs.
4. **Fix quyền**: `chown -R root:root`, `find ... -type d -exec chmod 755`, `-type f -exec chmod 644`.
5. **Verify trên host 2** (chạy lại script đếm qua SSH): 66 node / 51 config / 97 networks trùng khớp.
6. **Xóa thư mục tạm trên PC** (`Remove-Item -Recurse -Force`) — BẮT BUỘC sau mỗi lần đồng bộ xong.
7. Sau đó mới bàn tới image/addons (xem mục thiếu bên trên).

**Lưu ý host 2:**
- Các bản `.unl` cũ trên host 2 **ĐÃ XÓA 09/08/2026**: `Campus Network SDN SD-WAN.old-3107.unl` (bản 31/07, 65 node, không config nhúng) + thư mục `File/` (chứa `BK Campus Network SDN SD-WAN.unl`) — theo yêu cầu user chỉ dùng trực tiếp `.unl` từ host 1, không cần backup cũ. Host 2 giờ chỉ có `/opt/unetlab/labs/TranHuuNhan-PKT/` (lab đồng bộ từ host 1).
- Khi có thay đổi mới trên host 1 (sửa topo/config trực tiếp trên máy EVE): lặp lại quy trình 1–6 để host 2 luôn đồng bộ. Nếu thay đổi chỉ nằm trong repo (chưa đưa lên host 1) thì không cần đồng bộ host 2.
- Trạng thái lab trên host 2: **ĐÃ start 1 lần đầu 10/08/2026 (chỉ 10 node SDN) — xem "Trạng thái hiện tại"** — chưa từng wipe/start toàn lab. Lưu ý khi start qua CLI trên host 2: **dùng `-T 0`** (GUI EVE 6.7.5 host 2 quản lý lab ở **tenant 0**, console port qemu = `32768 + <node-id>`; IOL = `33536 + <node-id>`); `-T 6` tạo node song song ở tenant 6 → **TRÙNG qemu process + xung đột port console** (đã gặp node 3/4 chạy double 10/08).

## Trạng thái hiện tại (cập nhật sau mỗi phiên)

- **11/08/2026 (HOST 1 — SITE 300 ĐÀ NẴNG HOÀN THIỆN + LƯU RUNNING-CONFIG CẢ 3 CHI NHÁNH):** Cấu hình S300 theo RECIPE: tắt 8 node S400 (đã xong trước đó), start 8 node S300 (39,62,58,59,50,54,53,48) qua `-T 6 -D`; dán tay 3 IOL bổ sung `switchport trunk encapsulation dot1q`+`mode trunk` (config nhúng lại thiếu mode trunk, đúng quy luật S200): SwitchBrand-S300 (62): e0/0 trunk 80,90,99→FW, e0/1 80,99→SW58, e0/2 90,99→SW59, SVI 10.3.99.2; SW58: e0/0 trunk 80,99 + access 80→VPC50/54, SVI 10.3.99.11; SW59: e0/0 trunk 90,99 + access 90→VPC53/48, SVI 10.3.99.12 (write memory OK cả 3). FW 39: set enable password `vnpro@2026` (dùng drain-timing, kỹ thuật chờ idle giữa các prompt — xem lưu ý), dhcpd vlan80+90 Configured for DHCP SERVER, write memory 11688B. **DHCP verify**: VPC50=10.3.80.100, VPC54=.101, VPC53=10.3.90.100, VPC48=.101 (GW .1). **ĐÃ LƯU running-config thật vào configs/03-Site300-DaNang/** (SwitchBrand 96d/1215B, SW58/SW59 91d/1146B, Brand-FW 277d/11286B). **Trước đó cùng phiên**: lưu running-config thật S200 (02-Site200-CanTho: SwitchBrand 96d, SW55/SW56 91d, Brand-FW 277d) và S400 (04-Site400-NhaTrang: SwitchBrand 97d, SW60/SW57 90d, Brand-FW 277d — FW 38 cũng set enable password vnpro@2026 lần đầu + write memory 11688B). **CẢ 3 SITE CHI NHÁNH (200/300/400) ĐÃ HOÀN THIỆN + DHCP HOẠT ĐỘNG.** Lưu ý kỹ thuật telnet ASAv: màn hình "enable password is not set" khi vào enable lần đầu — gửi pwd → chờ thấy "Repeat Password:" → gửi lại → chờ prompt `#`; nếu gửi quá nhanh FW báo "Passwords do not match" và quay vòng — phải drain buffer tới khi console idle 1.2s mới gửi tiếp. Trạng thái lab: S300 đang chạy (39,62,58,59,50,54,53,48); S200 + S400 đã tắt.

- **11/08/2026 (HOST 1 — SITE 200 CẦN THƠ HOÀN THIỆN — DHCP HOẠT ĐỘNG):** Đã verify SDN còn sống trên host 1 (6/6 OVS kết nối controller 10.1.99.10:6653, echo OF 1.3 liên tục — tcpdump `IP 10.1.99.11/.12/.21-.24 > 10.1.99.10.6653`, capture 35s đủ 6 switch). Hoàn thiện campus Cần Thơ (S200) theo RECIPE: start 8 node (37,55,56,63,43,44,46,47) qua `unl_wrapper -a start -T 6 -D <id>`; **cấu hình tay 3 IOL qua telnet** (port `33536+id`) chèn `switchport trunk encapsulation dot1q` TRƯỚC `switchport mode trunk` (cả 3 cổng trunk thiếu `mode trunk` khi boot vì config nhúng cũ): SwitchBrand-S200 (63): e0/0 trunk 60,99→SW55, e0/1 trunk 70,99→SW56, e0/2 trunk 60,70,99→Brand-FW Gi0/0, SVI 10.2.99.2, vlan 60 NONG-NGHIEP/70 Y-TE/99 MANAGEMENT (`write memory` 808B); SW55 (55): e0/0 trunk 60,99, access 60→VPC43/44, SVI 10.2.99.11 (799B); SW56 (56): e0/0 trunk 70,99, access 70→VPC46/47, SVI 10.2.99.12 (798B). **Brand-FW-S200 (37)**: dhcpd vlan60+70 = "Configured for DHCP SERVER", sub-interface Gi0/0.60/.70/.99 `up/up`, lần đầu vào console bắt set enable password → đặt `vnpro@2026` (2 lần liên tiếp) rồi `write memory` (11688B). **Xác minh DHCP**: VPC43=10.2.60.100, VPC44=10.2.60.101, VPC46=10.2.70.100, VPC47=10.2.70.101 (GW+DHCP server .1, lease 3600) — khớp bảng 2.4. Lưu ý telnet python: IOL cần gửi Enter để hiện prompt `>`/`#`; VPC `ip dhcp` hiện menu help nghĩa là đã có IP — dùng `show ip`. S300 Đà Nẵng (39/62/58/59) vẫn CHƯA làm IOL tay — áp dụng RECIPE khi cần.

- **10/08/2026 (HOST 2 — PHIÊN TRIỂN KHAI SDN — ĐANG DỞ, sẽ tiếp tục phiên sau)**:
  - **Vấn đề gõ phím console VNC CHƯA GIẢI QUYẾT (blocker chính)**: node OVS/controller (linux-ubuntu-ovs-16p) dùng console `vnc` (port `32768+id`, RFB 003.008, không telnet). Dùng `vncdotool` (pip, Python PC) gõ phím bình thường thì **shell nhận toàn bộ chữ IN HOA** (`ls` → `Command 'LS' not found`, `id` → `ID: command not found`) dù đã: reset lshift/rshift/lctrl/lmeta press+release, toggle caplk (KEYMAP['caplk']=65509), OCR xác nhận không phải lỗi đọc. Chưa thử: gõ bằng cách nhấn `lshift` GIỮ + keyPress ký tự (có thể phải gõ bù ngược), hoặc dùng image console đổi sang telnet, hoặc paste script qua SSH từ host 2 vào node nếu image có sshd. Các node OVS còn đang BOOTING là bình thường (config="0" nên `.configured` không bao giờ xuất hiện — đừng chờ nó).
  - **Đã hoàn thành**: (1) 15 node có `.lock` kẹt (6,26–32,37–42,65) — đã `rm` sạch; (2) **ĐÃ VÁ cli.php host 2** (CAMPUS-PATCH giống host 1: `start()` tự `unlink .lock` khi getStatus()===1 — fix "Slim Application Error" khi double-click thiết bị trong GUI; backup gốc `/tmp/cli.php.bak_host2`, php -l OK); (3) Start 10 node SDN qua `unl_wrapper -a start -T 0`: **3,4 (Core, đã .configured + port 32771/32772 LISTEN), 5,8,9,24,66,68,69,70** — 9 node qemu + IOL 24 chạy OK; (4) **Stop các node còn lại** (user yêu cầu chỉ giữ node SDN — RAM host 2 chỉ 8GB, đã quá tải swap 2.4GB khi 48 qemu, load 29).
  - **Node cần giữ để làm SDN**: SDN_CONTROLLER 9 (VNC port 32777, RAM 4096), SwitchServerFarm 24, Core-SW1/2 3/4, Dist-SW1/2 5/8, Access-SW1–4 68/66/70/69. Script cấu hình trong repo: `configs/01-Site100-Campus/SDN_CONTROLLER.sh` (Ryu 6653/8080; **NIC i → ens(3+i)**: e0=ens3 (IP 10.1.99.10/24), e3=ens6 (Cloud-NAT, dhclient)), `Dist-SW1/2.sh`, `Access-SW1–4.sh` (add-br br0 + br-mgmt, trunks=10,20,30,40,90,99, dpid=node-id, set-controller tcp:10.1.99.10:6653, fail_mode=secure) — bấm vào từng node → past script.
  - **Trạng thái sau khi user tắt máy**: host 2 sẽ mất toàn bộ node đang chạy (CHƯA wipe, state qemu còn trong `/opt/unetlab/tmp/0/<uuid>` — có thể chạy lại nguyên vẹn). Phiên sau: start lại 10 node `-T 0` theo thứ tự Core(3,4) → SwitchServerFarm 24 → controller 9 → Dist 5/8 → Access 66/68/69/70, chờ boot, rồi cấu hình tay (xem blocker trên).
  - Lab UUID host 2: `ecf7c5b8-8c91-4616-953e-10b367b388e6` (lab đang chạy); còn 1 UUID cũ `e1f9795c-b4ac-4763-a0a6-db51b4967db9` (lab trước đó, để nguyên).

- HEAD: `c4a8e70` — nhúng 53 startup config base64 vào `.unl` (EVE chỉ nạp config từ phần nhúng này khi boot; trước đây GUI save làm reset cờ → Core-SW1 hostname vẫn "Switch"). Đã xác minh: Core-SW1 (node 3) boot ra prompt `Core-SW1>` sau wipe+start qua CLI. Trước đó `5222ac6`: bật lại `config="1"` 53 node; `31878c7`: VPC → DHCP, xóa nhãn IP PC, DHCP-Server = win server 2012 R2, xóa .unl.bak. (Từ 04/08/2026: `config="1"` còn **51 node** — đã xóa AccessTest 10 + VPC11/12.)
- Working tree **ĐANG sửa (07/08/2026, chưa commit)** — chuyển SDN control plane sang VLAN 99. Cấu hình còn lại cần làm TAY trên lab: vManager/vSmart/vBond GUI, Windows servers (IP tĩnh + role DHCP trên node 72, syslog/web/mail app trên Win7), OVS scripts, vEdge paste config, cài Win7 image đã sửa.
- **08/04/2026: sửa lỗi `.lock` kẹt hàng loạt** — 16 node (FW-ASAv 1,2; vEdge 6,28,29,30,31,40,41,42,65; Internet 26; MPLS 27; Brand-FW 37,38,39) có `.lock` kẹt từ 03/08 21:29 (cùng batch start cũ, stop 22:41 không dọn lock) → không start được. Đã `rm -f *.lock` + start lại qua unl_wrapper → tất cả RUN + LISTEN. Xác minh: ASAv 5 node `.configured`=YES; Internet/MPLS prompt `Internet>`/`MPLS>`; vEdge 9 node lên tới màn hình "Password:" boot đầu (cần dán config tay như ghi chú). Lab hiện có ~65 qemu process (toàn lab đã chạy).
- **04/08/2026 (working tree ĐANG sửa, chưa commit): triển khai SDN campus đầy đủ** — thêm 6 link control plane out-of-band vào `.unl` (network 100–105; SDN_CONTROLLER ethernet 2→8, thêm e1/e2/e4–e7; Dist-SW1/2 e8; Access-SW1–4 e5). Viết app mới `configs/01-Site100-Campus/campus_switch_13.py` (L2 học MAC theo VLAN + ACL proactive chặn VPC14 + ofctl_rest port 8080). Cập nhật script 6 switch: dpid, set-controller theo link riêng, fail_mode=standalone, stp_enable=true; Access-SW thêm IP mgmt 10.1.99.21–.24. Docs: md mục 2.7 mới, bảng 2.1.1/2.2.3/2.3.2/2.3.3, configs/README.md, HuondanchitietController_OVS.md PHẦN 3.
- **04/08/2026 (tiếp): ĐÃ XÓA AccessTest (10) + VPC11/12 (11, 12)** khỏi `.unl`: nodes + networks 97/98 + textobjects 167/168 + config nhúng id 11/12 (verify: 66 node, 102 network, `config="1"` = 51 đúng danh sách, XML hợp lệ). Đã xóa `configs/01-Site100-Campus/AccessTest.sh` + `VPC11/` + `VPC12/`; bỏ e3/192.168.100.1 khỏi `SDN_CONTROLLER.sh`; dọn AccessTest/VPC11/12 khỏi md (2.1.1, 2.2.3 #40–45, 2.3.2, 2.7), configs/README.md, HuondanchitietController_OVS.md (note ở PHẦN 3), SKILL.md, app `campus_switch_13.py` (bỏ dpid 10 khỏi PORT_CFG/docstring). **Còn việc tay trên lab (CHƯA LÀM)**: SCP .unl mới → stop nodes 10/11/12 → wipe+start 7 node (9,5,8,68,66,70,69) → chạy script `.sh` từng node → kiểm tra `is_connected: true` + `curl :8080/stats/switches` → test demo. SSH: root@10.215.28.26 (pass người dùng cấp từng phiên).
- **07/08/2026 (working tree ĐANG sửa, chưa commit): chuyển SDN control plane từ 6 link riêng sang VLAN 99 MANAGEMENT** (lý do: giảng viên hỏi vấn đáp về việc kéo dây riêng controller → từng switch). Xóa khỏi `.unl`: 6 network (100–105) + 12 interface (controller e1/e2/e4–e7, Dist-SW1/2 e8, Access-SW1–4 e5) → 66 node / 97 network, controller còn e0 (net 96) + e3 (net 106 Cloud-NAT). SDN_CONTROLLER e0 = **10.1.99.10/24** (SwitchServerFarm e1/0 access VLAN 99, bỏ VLAN 100 SDN-MGMT khỏi farm + trunk 2 Core); 6 switch OVS `set-controller br0 tcp:10.1.99.10:6653` (IP mgmt 10.1.99.11/.12/.21–.24 có sẵn VLAN 99). Đã sửa: `SwitchServerFarm/config.cfg`, `Core-SW1/2 config.cfg` (bỏ vlan 100, giữ trunk 90,99), `SDN_CONTROLLER.sh`, `Dist-SW1/2.sh`, `Access-SW1–4.sh`; docs md (2.1.1, 2.2.3, 2.3.2, 2.3.3, 2.7), configs/README.md, SKILL.md. **CHƯA ĐƯA LÊN EVE** (user tạm chặn push 07/08; lab vẫn đang chạy bản cũ).
- **07/08/2026 (máy EVE, CHƯA commit): SITE 400 NHA TRANG XONG — DHCP hoạt động**. Vá `.lock` trong `cli.php` (sửa gốc). Cấu hình tay 3 IOL qua telnet (config nhúng không tự nạp — xem "Lưu ý kỹ thuật"): SwitchBrand-S400 (id 64: trunk 50,60,99 lên Brand-FW e0/0; trunk 50,99→SW60; trunk 60,99→SW57; SVI 10.4.99.2), SW60 (id 60: vlan 50 THUY-SAN + trunk/access + SVI .11), SW57 (id 57: vlan 60 LU-HANH + trunk/access + SVI .12), đã `write memory` cả 3. Xác minh DHCP: VPC51=10.4.50.100, VPC45=10.4.50.101, VPC49=10.4.60.100, VPC52=10.4.60.101 (GW .1, dhcpd Brand-FW node 38). **RECIPE tái sử dụng cho site 200/300 đã ghi trong mục "RECIPE — Cấu hình campus chi nhánh" (node-id, cổng console, VLAN/SVI, quy trình 8 bước)**. Sites 200 (37/63/55/56) & 300 (39/62/58/59) CHƯA làm IOL tay — áp dụng recipe khi cần.
- **07/08/2026 (máy EVE, CHƯA commit): FIX Core-SW1/2 "CPU hog" — đã khắc phục** (chi tiết ở "Lưu ý kỹ thuật lab" mục viosl2): Core-SW1 (node 3) + Core-SW2 (node 4) đều ra prompt bình thường trở lại. LƯU Ý ĐỒNG BỘ: `.unl` trên server hiện có node 3 = qemu_version 3.1.0 (sửa tạm khi chẩn đoán) — khi nào up config cần đưa node 3 về qemu 2.4.0 + `-cpu host` khớp thiết kế gốc (backup `/tmp/unl.bak_qemu` = bản gốc).
- **09/08/2026 (HOST 2 DỰ PHÒNG ĐÃ ĐỒNG BỘ XONG)**: copy topo + config từ host 1 (10.215.28.26) → host 2 (IP cũ 10.0.239.137, nay mới 192.168.2.18; EVE 6.7.5, root/eve) qua PC trung gian (host1→host2 không reach trực tiếp). Kết quả trên host 2 `/opt/unetlab/labs/TranHuuNhan-PKT/`: .unl 66 node / 97 network / 51 config nhúng + 53 thư mục node config, XML hợp lệ, quyền root:root đã fix. **ĐÃ XÓA các bản .unl cũ + backup trên host 2** (`.old-3107.unl` và thư mục `File/`) — user chỉ dùng trực tiếp .unl host 1, không giữ bản cũ. Thư mục tạm PC đã xóa. **10/08/2026: user TỰ tải 2 image còn thiếu lên host 2, đã verify đầy đủ + khớp size host 1** (`linux-ubuntu-ovs-16p` 3.0G, `winserver-S2012-R2-x64` 4.5G). Host 2 giờ có đủ toàn bộ image — sẵn sàng start lab. Chưa wipe/start node nào trên host 2.

## Lưu ý kỹ thuật lab

- **VNC console node linux (OVS/controller) — gõ phím tự động qua vncdotool BỊ IN HOA (10/08/2026, chưa giải quyết)**: console port qemu tenant 0 = `32768+id`; handshake `RFB 003.008` OK; `vncdotool api.connect(host::port)` + `keyPress(char)` từng ký tự → shell nhận UPPERCASE hoàn toàn. Đã thử reset modifiers (keyDown/keyUp lshift/rshift/lctrl/rctrl/lalt/ralt/lmeta/rmeta), toggle caplk — không hết. Hướng thử tiếp phiên sau: (a) giữ lshift DOWN trong lúc gõ từng ký tự (shift+letter = chữ thường nếu caps đang bật); (b) `command.py` vncdotool có flag `--force-caps` (factory.force_caps) — thử cả 2 trạng thái; (c) check `setxkbmap`/keymap trong VM qua OCR; (d) đổi console node sang `telnet` trong .unl tạm + restart node. OCR đọc console: `pip install pytesseract` + tesseract v5.4 (winget UB-Mannheim.TesseractOCR), scale ảnh x3 + `--psm 6`.
- Node 72 RAM 8GB, node Windows khác 4GB (image win-7 x86, ram 4096).
- Sau khi đổi config trên EVE phải Wipe node để nạp lại.
- VPC xin DHCP cần server đã boot xong; nếu chưa, gõ lại `ip dhcp` trong console vpcs.
- **Mật khẩu admin dùng chung**: username `admin`, password **`vnpro@2026`** — đã đặt cho cả 5 node ASAv (FW-ASAv-Active 1, FW-ASAv-Standby 2, Brand-FW 37/38/39) và **9 node vEdge (6, 28, 29, 30, 31, 40, 41, 42, 65)** ngày 08/04/2026 (vEdge: tự động nhập qua console 2 lần Enter/Re-enter password, thành công ra prompt `vedge#`). Lưu ý: vEdge từ chối mật khẩu có 3 ký tự lặp/liên tiếp ASCII (vd `abc`, `123`, `aaa`); màn hình đặt mật khẩu vEdge sẽ tự quay vòng "did not match" nếu 2 lần nhập khác nhau — chỉ cần gửi PWD 2 lần liên tiếp khi gặp prompt `Password:`/`Re-enter password:`.

- **Node start "im lặng" (không lên, không lỗi)**: nguyên nhân thường là file `.lock` kẹt (0 byte) trong `/opt/unetlab/tmp/6/<lab-uuid>/<node-id>/`. `__node.php getStatus()`: port console không LISTEN + có `.lock` → status=1 "stopped and locked"; `cli.php start()` chỉ start khi status==0 → trả về 0 không làm gì (exit code 0 đánh lừa). **Fix**: `rm -f <node-dir>/.lock` rồi start lại qua `unl_wrapper -a start -T 6 -F "....unl" -D <id>`; verify qemu chạy + port `32768+128*6+id` LISTEN + file `.configured` xuất hiện sau ~1-2 phút. Đã gặp ở Core-SW2 (node 4) 08/04: xóa .lock là lên ngay, config nhúng nạp đúng (prompt `Core-SW2>`). **Scan nhanh toàn lab**: với mỗi node dir, nếu có `.lock` và port `33536+id` không LISTEN → bị kẹt (16 node từng dính cùng lúc 08/04).
- **Đã vá gốc `.lock` (07/08, máy EVE)**: lỗi kẹt lock hàng loạt là do **config-import tạo `.lock` mà không xóa** khi node console kiểu VNC/RFB (vEdge/Internet/MPLS/OVS — không telnet nên script `config_*.py` không chạy được để dọn lock). Vá `/opt/unetlab/html/includes/cli.php` trong hàm `start()`: trước khi start, nếu `getStatus()===1` (stopped+locked) thì `unlink .lock` — node vẫn start bình thường. Backup gốc `/tmp/cli.php.bak` (bản date 07/08). Verify: cycle stop→start→stop node 28 OK, 11 node WAN (6,26–31,40–42,65) stop sạch không còn lock.
- **IOL switch (SwitchBrand-SW/SWxx) KHÔNG tự nạp config nhúng khi start qua CLI** (07/08): dù `.unl` có config nhúng + `config="1"`, sau wipe+start node 64 boot ra config mặc định (chỉ VLAN 1, hostname lấy từ node name); SW60/57 cũng thiếu `switchport mode trunk`/`name`. **Phải dán tay qua telnet console** (đúng "Cách B"): `enable` (không có pass) → `configure terminal` → dán từng dòng (pause ~0.3–0.5s) → `end` → `write memory`. **IOL bắt buộc `switchport trunk encapsulation dot1q` TRƯỚC `switchport mode trunk`** (image l2 không nhận "Auto" → "Command rejected"). Dùng `terminal length 0` trước `show running-config` để không bị cắt `--More--`; config IOL lưu dạng compress-config (running ~1276B → nvram ~813B).
- **VPCS `ip dhcp`**: thành công khi DHCP server sẵn sàng; nếu `IP ... dhcp` hiển thị lại menu trợ giúp nghĩa là đã có IP (thoát menu). Câu lệnh kiểm tra: nhập `ip dhcp` rồi `ip` (IP/mask/GW hiện ra).
- **viosl2 (Core-SW1/2, node 3/4) crash loop "CPU hog" — KHẮC PHỤC XONG 07/08/2026**: triệu chứng console telnet chỉ ra `-Traceback= ... Process "IOSv e1000"/"Net Input"/"IOSv in console", CPU hog, PC 0x00981D25/0x0095FC39` lặp lại trên mỗi Enter, qemu chạy ~105% CPU, không bao giờ ra prompt. Nguyên nhân gốc: **driver e1000 của image viosl2 bị sập khi nhận traffic broadcast/ARP storm từ các OVS switch nodes** (Dist-SW1/2 node 5/8, Access-SW1–4 node 68/66/70/69) gửi vào qua các Linux bridge (STP OFF, MTU 9000) — xảy ra khi core switch khởi động TRONG lúc các OVS nodes đang chạy.
  - **Đã loại trừ (không phải nguyên nhân)**: qemu_version 2.4.0 → 2.12.0 → 3.1.0, `-cpu host` → `qemu64`, tap MTU 9000 → 1500 — đều vẫn hog khi có traffic OVS.
  - **Xác minh khoa học**: bỏ hết NIC (xóa interfaces khỏi .unl tạm thời) → boot OK prompt `Core-SW1>` sau ~77s; dừng 6 node OVS → boot OK; start lại từng node OVS → core vẫn sống. Kết luận: chỉ traffic OVS lúc boot mới gây sập.
  - **Cách khắc phục (start order)**: start core switch TRƯỚC hoặc SAU khi các OVS nodes đã boot xong và traffic ổn định — nếu core bị hog: `unl_wrapper -a stop -D 3/4` → stop 6 node OVS (5,8,66,68,69,70) → start core → chờ prompt OK → start lại OVS. Node 4 (Core-SW2) dùng qemu 2.4.0 gốc vẫn boot OK khi dừng OVS — không cần đổi qemu.
  - **Trạng thái cuối 07/08**: Core-SW1 + Core-SW2 đều ra prompt `Core-SW1>`/`Core-SW2>` bình thường, 6 OVS nodes đã start lại, lab ổn định. Lưu ý: .unl trên server đã được sửa tạm (qemu 3.1.0 node 3) trong lúc chẩn đoán — **đồng bộ lại .unl repo → server khi có dịp** (node 3 nên về qemu 2.4.0 + `-cpu host` cho khớp thiết kế gốc).
