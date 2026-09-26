# Session Summary — 19/09/2026

## Chủ đề: Xử lý L2 loop VLAN99 làm OVS (dpid 5, 8) không connect controller

### Bối cảnh kế thừa (từ session 18/09)
- Node 5 (Dist-SW1) và node 8 (Dist-SW2) không connect controller 10.1.99.10:6653; VLAN99 bị loop → STP + fullmesh IOL.
- Root cause phát hiện 18/09: trên Core-SW1/Core-SW2 (live, KHÔNG có trong repo config.cfg) có `no spanning-tree vlan 99` → VLAN99 chạy full-mesh không STP → broadcast storm.
- User chốt hướng (session này): **điều chỉnh thiết kế, vừa khắc phục loop vừa đúng chuẩn campus/doanh nghiệp hiện đại** — prune VLAN99 về đúng "cây quản trị" deterministic + bật lại STP vlan99 (defense-in-depth), test: node 5/8 connect controller.

### Thiết kế chuẩn VLAN99 (đã chốt — khớp app `campus_switch_13.py` `VLAN99_TREE_BLOCK` dòng ~100–130)
- Cây mgmt hợp lệ: `Controller → Farm (e1/0 → e0/0) → Core-SW1 (Et1/1) → Core-SW1 (Et1/2) → sw8 (ens10) → sw8 (ens8) ↔ sw5 (ens8) → sw5 (ens4→e7...) → Access`.
- Các nhánh KHÔNG được mang VLAN99 (prune `switchport trunk allowed vlan remove 99`):
  - Core-SW1 Et0/2 (→ sw5.ens9) — theo app: "STP Core-SW1 chan vlan99 tren Et0/2"
  - Farm E0/3 (→ Core-SW2 Et1/1) — theo app: "Farm chan nhanh Core-SW2 cho vlan99"
  - Core-SW2 Et0/2 (→ sw8.ens9) — "Dist-SW2 -> Core-SW2 ... khong nam trong cay mgmt"
  - Core-SW2 Et1/2 (→ sw5.ens10) — "Dist-SW1 -> Core-SW2 ... khong nam trong cay mgmt"
- STP vlan99: bỏ `no spanning-tree vlan 99` trên Core-SW1/2; Core-SW1 = secondary root (priority 8192), Core-SW2 = 12288. (Farm giữ root ngầm feature.)

### Việc ĐÃ LÀM LIVE (EVE host 10.215.28.26, tool C:\Users\nhanh\AppData\Local\Temp\opencode\telnet_ios.py)
1. **Core-SW1 (port 33539)** — bật lại STP vlan99 + priority 8192; sau đó prune Et0/2:
   `spanning-tree vlan 99`, `spanning-tree vlan 99 priority 8192`, `interface Ethernet0/2 → switchport trunk allowed vlan remove 99`, `end`, `write memory` (config compress từ 3309→1770B).
2. **Core-SW2 (port 33540)** — prune cả 3 cổng quan trọng:
   `interface Ethernet0/2` (→ sw8.ens9) remove 99, `interface Ethernet1/1` (→ Farm) remove 99, `interface Ethernet1/2` (→ sw5.ens10) remove 99, sau đó `spanning-tree vlan 99` + `spanning-tree vlan 99 priority 12288`, `end`, `write memory`. (Lần telnet đầu bị timeout giữa chừng do dùng lệnh liên tiếp — shell timeout 120s; đã chạy lại các lệnh còn lại riêng từng cụm.)
3. **Farm/SwitchServerFarm (port 33560)** — `interface Ethernet0/3` (→ Core-SW2) `switchport trunk allowed vlan remove 99`, `write memory` (2053→1190B).
   - Verify live trunk Farm: Et0/0 = 90,99 (GIỮ — đường mgmt chính), Et0/3 = 90 (đã bỏ 99).

### Đo traffic KHÔNG giảm dù đã prune IOL (quan trọng!)
- Đo 3s sau khi prune (tap = `vunl6_<node>_<iface-index>`):
  - vunl6_3_32/vunl6_5_6 (Core-SW1 Et0/2 ↔ sw5.ens9): ~133–135k pps, hầu hết **vlan 99**
  - vunl6_8_7/vunl6_3_33 (Core-SW1 Et1/2 ↔ sw8.ens10): ~154–172k pps, vlan 99
  - vunl6_8_6/vunl6_4_32 (Core-SW2 Et0/2 ↔ sw8.ens9): ~139–145k pps, vlan 99
  - vunl6_5_7/vunl6_4_33 (Core-SW2 Et1/2 ↔ sw5.ens10): ~157k pps, vlan 99
  - **vunl6_5_5/vunl6_8_5 (inter-dist sw5.ens8 ↔ sw8.ens8)**: ~249k pps, vlan 99 — NÓNG NHẤT
- ARP detail trên vunl6_3_33: `aa:bb:cc:80:36:00 > 00:50:06:00:09:00, vlan 99, ARP Reply 10.1.99.1 is-at aa:bb:cc:80:36:00` lặp ~20µs.
- Controller (eve_node9.py, node 9): `curl -s http://10.215.28.56:8080/stats/switches` = **RONG** (không switch nào connect).
- **KẾT LUẬN SƠ BỘ**: vòng lặp còn tồn tại ngoài IOL → nằm ở **lớp OVS bootstrap**. Đang điều tra: restore script và env.

### Phát hiện khi debug bootstrap OVS (đang trong quá trình điều tra)
- `configs/01-Site100-Campus/Campus-OVS-restore.sh`:
  - Dòng 89: vẫn add flow `priority=50000,dl_vlan=99,actions=NORMAL` → đây LÀ THỦ PHẠM nghi vấn (NORMAL = tự học fullmesh trên mọi cổng trunk99).
  - Comment dòng 96–99 đã NÓI RÕ: "Bootstrap only a loop-free VLAN 99 tree. NORMAL cannot be used here: all six OVS nodes start before Ryu can install TREE-BLOCK rules, so NORMAL briefly recreates the dual-home/full-mesh loop and datapaths flap before the controller can take ownership." → **ĐÍCH PHẢI LÀ LOẠI BỎ flow NORMAL vlan99 khi bootstrap, thay bằng cây pruned**.
  - `CAMPUS_BOOTSTRAP99_PORTS` được khai trong /etc/default/campus-ovs nhưng script dòng 17–25 chỉ **check tồn tại**, CHƯA dùng để dựng flow cây.
- Env hiện tại (repo `configs/.../systemd/ovs-nodes/*.env`):
  - Dist-SW1: `CAMPUS_BOOTSTRAP99_PORTS="patch-mgmt ens8"` (chỉ ens8 inter-dist + patch-mgmt)
  - Dist-SW2: `CAMPUS_BOOTSTRAP99_PORTS="patch-mgmt ens8 ens10"` (ens8 inter-dist + ens10 → Core-SW1 + patch-mgmt)
  - Access-SW1..4: `CAMPUS_BOOTSTRAP99_PORTS="patch-mgmt ens4"` + `CAMPUS_BOOTSTRAP99_FAILOVER_PORTS="patch-mgmt ens5"`
  - Nhưng **TRUNK99_PORTS vẫn = ens4..10 (fullmesh) trên Dist** → khi flow NORMAL được add, vlan99 được bridge khắp mọi cổng trunk99 → vòng lặp vẫn chạy dù đã prune IOL.
- Đề xuất fix sắp tới: sửa restore.sh để khi chưa có controller — KHÔNG add NORMAL toàn cổng; thay bằng flow hạn chế đúng `CAMPUS_BOOTSTRAP99_PORTS` (hoặc để cổng down) cho tới khi Ryu quản lý. Cần verify với user trước khi sửa (rủi ro: OVS không tự học → cần controller sớm).

### Cảnh báo / kỹ thuật đã đúc kết thêm
- **Tap EVE = `vunl6_<node>_<iface-index>`** (KHÔNG phải network-id). Ánh xạ:
  - node5: e5=ens8 inter-dist ↔ node8 e5=ens8; e6=ens9→Core-SW1 Et0/2; e7=ens10→Core-SW2 Et1/2; e1..e4 = ens4..7 → Access.
  - node8: e7=ens10→Core-SW1 Et1/2; e6=ens9→Core-SW2 Et0/2; e5=ens8 inter-dist; e1..e4 → Access.
  - Core-SW1: Et0/2=iface32 (net28), Et1/1=iface17 (net38↔Farm E0/0), Et1/2=iface33 (net30↔sw8.ens10).
  - Core-SW2: Et0/2=iface32 (net29↔sw8.ens9), Et1/1=iface17 (net55↔Farm E0/3), Et1/2=iface33 (net31↔sw5.ens10). Po10 giữa 2 core = L3 (ida 16/48), không phải đường vòng vlan99.
- Telnet_ios.py: nếu dùng 1 shell gõ nhiều lệnh liên tiếp dễ timeout (120s) → tách nhỏ hoặc tăng timeout; session telnet có thể bị kẹt ở config mode → gõ `end` trước `show`.

### VIỆC CÒN LẠI (ưu tiên)
1. (THEO XÁC MINH) Sửa `Campus-OVS-restore.sh` — đừng add `NORMAL` toàn cổng; dựng flow cây VLAN99 theo `CAMPUS_BOOTSTRAP99_PORTS` cho tới khi controller tiếp quản; deploy lên 6 node OVS (cách: qua .env + scp/restart service per node).
2. Verify lại IOL: `show interfaces trunk` Core-SW1/2 + Farm (đã prune), `show spanning-tree vlan 99` (Core-SW1 secondary, Core-SW2 khác).
3. Sau khi bootstrap đúng: đợi controller REST `/stats/switches` hiện 6 dpid; kiểm tra ryu.log; node 5/8 connect.
4. Nếu vẫn loop: capture src MAC trên vunl6_5_5 để tìm MAC nguồn vòng (đã thấy `aa:bb:cc:80:36:00` = SVI core 10.1.99.1).
5. Đồng bộ config.cfg Core-SW1/Core-SW2/Farm trong repo cho khớp live (thêm `spanning-tree vlan 99 ...`; bỏ vlan99 khỏi các cổng đã prune).