---
name: campus-network-lab
description: Trợ lý cho đồ án "Campus Network kết hợp SDN + SD-WAN" trên EVE-NG (4 campus, Ryu/OpenFlow/OVS, Viptela vManage/vSmart/vBond/vEdge, ASAv HA, IOL, DHCP). Dùng khi làm việc với Campus Network SDN SD-WAN.unl, configs/, campus_network_sdn_sdwan.md, node-id/IP/VLAN/ASN, console thiết bị, cấu hình nhúng EVE-NG, Ryu–OVS, vEdge không lên controller, DHCP không cấp, đồng bộ host EVE, hoặc báo cáo/slide/tiến độ của đồ án.
---

# Campus Network SDN + SD-WAN Lab

Đồ án của Trần Hữu Nhân và Nguyễn Nhật Hào: mô phỏng 4 campus (Site 100 chính, 200 Cần Thơ, 300 Đà Nẵng, 400 Nha Trang) + site controller 900 trên **một lab EVE-NG**. SDN = Ryu điều khiển 6 OVS của Site 100 qua VLAN 99. SD-WAN = Viptela 20.10.1, transport Internet + MPLS, underlay BGP.

**Ngôn ngữ**: trả lời và viết tài liệu bằng **tiếng Việt**, giữ thuật ngữ kỹ thuật tiếng Anh.

## Bắt đầu mỗi tác vụ

1. `git status --short` — bảo toàn mọi thay đổi chưa commit của người dùng (hiện có nhiều: xem `project-status.md`).
2. Đọc **nguồn thật** liên quan trước khi kết luận: `.unl` (node/link/config nhúng) → `configs/` → `campus_network_sdn_sdwan.md` (thiết kế) → `configs/README.md` (node-id). Mâu thuẫn giữa nguồn ⇒ nêu rõ và kiểm chứng; không chọn dữ liệu cũ chỉ vì nó nằm trong ghi chú.
3. Nhớ rằng `references/project-status.md` là **snapshot có ngày**; trạng thái live phải kiểm lại.
4. Sau khi làm xong, cập nhật snapshot nếu có thay đổi đáng kể — đừng viết nhật ký vào file này.

## Chọn tài liệu tham chiếu

| Việc | Đọc |
|---|---|
| Kiến trúc, IP/VLAN/ASN, **node-id**, quyết định đã chốt, image IOL | [topology-and-conventions.md](references/topology-and-conventions.md) |
| Sửa `.unl`, config nhúng, đồng bộ host↔repo, deploy, wipe/start, `.lock`, host 2, vManage GUI từ xa | [eve-ng-ops.md](references/eve-ng-ops.md) |
| Gõ lệnh qua console (telnet/VNC/serial), hành vi từng nền tảng, tài khoản | [console-automation.md](references/console-automation.md) |
| Ryu, OVS, VLAN 99 loop, DHCP không cấp, khôi phục OVS | [sdn-ryu-ovs.md](references/sdn-ryu-ovs.md) |
| vEdge không lên controller, PKI/CSR, whitelist, onboard, màu TLOC, BGP | [sdwan-viptela.md](references/sdwan-viptela.md) |
| Chi nhánh 200/300/400, FW HA/ASDM, DHCP-Server, Web/Mail/Syslog, Core IOL | [branch-and-services.md](references/branch-and-services.md) |
| Báo cáo LaTeX, slide, bảng tiến độ, demo | [deliverables.md](references/deliverables.md) |
| Ta đang ở đâu, việc còn dở | [project-status.md](references/project-status.md) |

Chỉ đọc file cần cho tác vụ. Mỗi file có mục lục ở đầu.

## Công cụ cục bộ

`python .claude/skills/campus-network-lab/scripts/unl_tool.py <lệnh>` (chỉ đọc/ghi file local, không chạm EVE):
- `validate` — **chạy sau mọi thay đổi `.unl`**: XML, ID trùng, network treo, đúng 51 `config="1"`, config nhúng hợp lệ.
- `drift` — config nhúng vs `configs/` (hiện lệch 12/51).
- `nodes` — bảng node/image/port console; `dump <id>`; `embed <id> <file> [--write]` (thay khối ở mức byte, mặc định dry-run).

## Bất biến cốt lõi (phải giữ)

- **IP**: octet 2 = site (1/2/3/4/9); VLAN `/24`, gateway `.1`, server `.10/.11`, **DHCP pool `.100–.199`**; System-IP OMP `10.200.<site>.x` (300→`30`, 400→`40`, 900→`90`); Internet `203.0.113.0/24`, MPLS `100.64.x.x/30`.
- **Control plane SDN** = VLAN 99 (`10.1.99.0/24`, controller `10.1.99.10:6653`); không có mạng điều khiển riêng; không khôi phục `10.1.100/101.0/24`, `192.168.100.0/24`.
- **Node dễ nhầm**: Access-SW1 **68**, Access-SW2 **66**, Access-SW3 **70**, Access-SW4 **69**; vEdge2 S200/S300/S400 = **42/40/41**; Brand-FW S200/S300/S400 = **37/39/38**; DHCP-Server **72**. Tên node trong `.unl` trùng nhau → dùng **id**. Bảng đầy đủ ở `topology-and-conventions.md`.
- `.unl` giữ đúng **51** node `config="1"` (=51 config nhúng); `config="0"` cho Windows, vtmgmt/vtsmart/vtbond, Linux/OVS. Không tạo `.unl.bak`. Sửa `.unl` **ở mức byte**.
- Ryu/OVS: giữ `tag=/trunks=`, `OpenFlow13`, `fail_mode=secure`, `stp_enable=false`, OF1.3 dùng `vlan_vid` (không `dl_vlan`).
- Chi nhánh = Firewall-as-Core; Core-SW1/2 = IOL (`vtp mode off` + `trunk encapsulation dot1q` trước `mode trunk`); underlay = BGP; DHCP-Server node 72 (Win Server 2012 R2).
- **Không lặp lại** thứ đã xoá/từ chối: AccessTest 10, VPC11/12, node 23, OSPF underlay, SwitchBrand làm router.

## Quy trình thay đổi

1. Xác định phạm vi ảnh hưởng.
2. Sửa nguồn trong `configs/`.
3. Đồng bộ thứ phụ thuộc: thiết kế/IP/link → `campus_network_sdn_sdwan.md`; node-id/deploy → `configs/README.md`; topology → chỉ `Campus Network SDN SD-WAN.unl`; config nạp tự động → **cả** file nguồn **và** khối `<config>` nhúng (`unl_tool.py embed`).
4. `unl_tool.py validate` (+ `drift`), rồi `git diff` chỉ trong phạm vi.
5. Tóm tắt: file đổi, kiểm tra đã chạy, việc thủ công còn lại, phần chỉ xác minh được trên EVE thật.

## Chẩn đoán: theo lớp, dừng ở lớp đầu tiên sai

Vật lý/link → L2 (VLAN, trunk, STP/loop) → L3 (gateway, route, BGP) → dịch vụ (DHCP/relay, control connection) → ứng dụng. Có capture/`show` làm bằng chứng cho mỗi kết luận; không sửa vơ vẩn, không paste lại cả cấu hình khi một dòng sai. Ví dụ đã làm mẫu: DHCP theo 4 lớp A–D (`sdn-ryu-ovs.md`), vEdge theo bảng dấu hiệu → nguyên nhân (`sdwan-viptela.md`).

## Rào an toàn (thứ tự quan trọng)

- **Hỏi trước** khi: commit/push; SCP/ghi lên EVE; wipe/start/stop node; xoá `.lock`; đổi config live trên thiết bị; xoá bridge OVS. Việc cục bộ, chỉ đọc, thì cứ làm.
- **Host 1 là nguồn chuẩn, đồng bộ một chiều host 1 → repo.** Cấm đẩy `.unl`/config từ repo lên host 1 khi người dùng chưa cho phép rõ ràng.
- **Cấm wipe** node `config="0"` (OVS, controller, DHCP-Server, vManager/vSmart/vBond, Windows) — mất sạch cấu hình tay. Cấm chu kỳ Delete lab → Import; cấm mở/save lab bằng GUI EVE.
- **Mật khẩu**: lưu cục bộ ở `C:\Users\nhanh\.claude\campus-lab-credentials.md` (ngoài repo và ngoài OneDrive). **Đọc file đó khi cần đăng nhập thiết bị — không hỏi lại người dùng.** Chỉ hỏi cho mục ghi "CHƯA CÓ", rồi ghi giá trị mới vào chính file đó. Tuyệt đối không chép giá trị vào skill, repo, file trong `configs/`/`HuongDan/`, commit, log hay tin nhắn trả lời; trong script đọc từ file/biến môi trường lúc chạy, không đặt trong command line hoặc nhúng cứng. Khi báo cáo kết quả chỉ nêu "đăng nhập OK", không in mật khẩu. Nếu file không tồn tại (máy khác), hỏi người dùng.
- **Rò rỉ đã xảy ra**: `.opencode/skills/campus-network-lab/SKILL.md` (có mật khẩu lab) nằm trong commit `9a97537` đã đẩy lên `origin/main`; nhiều file `configs/`, `campus_network_sdn_sdwan.md`, `HuongDan/` cũng chứa mật khẩu thiết bị. Không commit thêm file có mật khẩu; nếu người dùng chia sẻ repo, nhắc đổi mật khẩu lab.
- Không tin exit code của `unl_wrapper`/script — xác minh bằng prompt, process, port, output `show`.
- Không suy tính năng IOL từ tên image; không `pkill -f "chuỗi có trong chính lệnh"`; login sai nhiều lần khoá tài khoản ~15 phút.
- Node Windows/VNC: thao tác GUI do người dùng làm.

## Tiêu chí hoàn tất

- `validate` ĐẠT; thiết kế, `.unl`, `configs/`, bảng node-id không mâu thuẫn trong phạm vi thay đổi; không mất/ghi đè thay đổi không liên quan.
- Bằng chứng live cho mọi khẳng định "đã chạy" (prompt, `show`, capture); phần chưa xác minh được nói rõ, không báo xong theo suy đoán.
- Nếu trạng thái dự án đổi đáng kể, `project-status.md` được cập nhật (có ngày).

## Bảo trì skill

Giữ SKILL.md ngắn; kiến thức chi tiết vào `references/`. Khi phát hiện sự thật mới hoặc điều đã sai: sửa **tại chỗ** trong file chủ đề (không thêm mục nhật ký chồng chéo). Bảng node-id và invariant 51 node là chỗ dễ lệch nhất — đối chiếu bằng `unl_tool.py nodes`/`validate`.
