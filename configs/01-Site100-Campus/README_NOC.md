# Campus SDN Console – giao diện tập trung đo đạc & đánh giá SDN (Site 100)

Hai app Ryu chạy cùng tiến trình trên **SDN_CONTROLLER (node 9, 10.1.99.10)**:

| File | Vai trò |
|---|---|
| `campus_switch_13.py` (v2, 10/2026) | Điều khiển: L2 theo VLAN, **cây dữ liệu tính tập trung** trên đồ thị liên kết, **thăm dò liên kết chủ động**, VLAN 99 tĩnh có hướng, nhật ký sự kiện + đo thời gian hội tụ |
| `campus_noc_monitor.py` (v2) | Giao diện **Campus SDN Console** + REST + đo lưu lượng (PortStats) + **ping liên tục** từ controller |

```
ryu-manager --ofp-tcp-listen-port 6653 campus_switch_13.py campus_noc_monitor.py ryu.app.ofctl_rest
```
(`SDN_CONTROLLER-autostart.sh` / `campus-ryu.service` tự nạp NOC nếu file tồn tại.)

## Truy cập giao diện

- Từ PC-Management (VLAN 99): `http://10.1.99.10:8080/`
- Từ laptop qua host 1 (node 9 có IP LAN ở `ens6`, hiện `10.215.28.71`, DHCP – có thể đổi):
  `ssh -L 8080:10.215.28.71:8080 root@<host1>` rồi mở `http://localhost:8080/`
- Không dùng CDN (VLAN 99 không ra Internet): biểu đồ vẽ bằng canvas trong trang.

## Các tab và mục tiêu đánh giá

| Tab | Nội dung | Mục tiêu đề bài |
|---|---|---|
| Tổng quan | Switch/liên kết sống, hội tụ gần nhất & trung bình, băng thông tổng | – |
| Topology | Sơ đồ liên kết: thuộc cây / dự phòng / chết / đang mô phỏng cắt; nút **Cắt/Khôi phục** từng liên kết (silent / admin) | 2 |
| Khôi phục | Ping liên tục từ controller (chu kỳ 0,1–1 s), RTT + vùng mất gói, bảng sự kiện `detect/converge/total`, xuất CSV | 2 |
| Lưu lượng | Mbps từng switch theo thời gian, bảng cổng (Mbps, pps, drop, %) | 4 |
| VLAN | Thêm/xoá VLAN, gán cổng access trên Access (1 lệnh API), lịch sử thời gian triển khai, **đoạn IOS cho Core-SW1/2 do controller sinh**, bảng so sánh với cấu hình truyền thống | 1 |
| Chính sách | Thêm luật deny/allow (VLAN `vlan:N`, CIDR, IP; ip/icmp/tcp/udp; cổng; hai chiều; ưu tiên), bật/tắt/xoá, **bộ đếm gói khớp từng luật**, lịch sử thời gian áp toàn campus, mẫu dựng sẵn | 5 |
| Tải thiết bị | Từng Dist/Access: Mbps, pps, drop, **packet-in/s**, số flow bảng 0/1, lookup/s (TableStats); Core-SW1/2: lưu lượng qua uplink OVS (+ CPU qua SNMP nếu cấu hình `state/snmp.json`); CPU/RAM node 9 và tiến trình Ryu | 4 |
| Hiệu năng | Ma trận RTT VLAN×VLAN (trong VLAN = L2 qua OVS, khác VLAN = qua Core), chi tiết cặp, lịch sử; nút bật ping liên tục từ controller tới mỗi VLAN | 3 |

## REST

| Endpoint | Ý nghĩa |
|---|---|
| `GET /noc/summary` | Tổng hợp (switch, liên kết, gốc cây, hội tụ gần nhất/trung bình, BW) |
| `GET /noc/switches`, `/noc/ports`, `/noc/congestion`, `/noc/history` | như phiên bản 1 (PortStats nay được poll định kỳ 5 s) |
| `GET /campus/topology` | Đồ thị: nút, liên kết (`up`, `in_tree`, tuổi probe), cổng bị chặn, VLAN, tham số thăm dò |
| `GET /campus/events?since=N` | Sự kiện: `link_down/up`, `switch_down/up`, `tree_change`, `test_inject/restore` kèm `detect_ms`, `converge_ms`, `total_ms`, `switches`, `flow_mods`, `announced`, `unanswered` |
| `POST /campus/linktest` | `{"link":"A1-D1","action":"down|up","mode":"silent|admin","max_s":60}` – silent tự hết hạn trên OVS sau `max_s` (5–600 s, `hard_timeout`); admin bị từ chối trên cổng thuộc đường VLAN 99 |
| `GET /campus/vlans` | VLAN, cổng access, cổng trống trên Access |
| `POST /campus/vlan` | `{"action":"add|ports|delete","vid":50,"name":"Phong Lab","ports":["Access-SW1.ens7"]}` → sự kiện `vlan_*` (thời gian tới barrier) + `core_config` (IOS cho Core-SW1/2) |
| `GET /campus/policies` | Luật + `packets`/`bytes` khớp (FlowStats theo cookie, 5 s) |
| `POST /campus/policy` | `{"action":"add","rule":{"action":"deny","src":"vlan:10","dst":"vlan:40","proto":"icmp","bidir":true,"prio":100}}`; `{"action":"delete|enable|disable","id":1}` |
| `GET /campus/load?n=120` | Mẫu tải 5 s: `sw` (từng switch), `core` (uplink + CPU SNMP), `ctl` (CPU/RAM, packet-in/s) |
| `GET /campus/perf`, `POST /campus/perf` | Kết quả đo ma trận VLAN (script lab đẩy lên `{rows:[...]}`), lưu `metrics/perf.json` |
| `GET/POST /campus/pinger` | `{"target":"10.1.40.102","action":"start|stop|reset|remove","interval":0.1}` |
| `GET /campus/export/events.csv`, `/campus/export/pinger.csv?target=IP` | Xuất CSV cho báo cáo |

## Cách đo (mục tiêu 2 – thời gian khôi phục)

- **detect** = mốc phát hiện − mốc kích hoạt (lúc bấm mô phỏng, hoặc lần cuối thấy probe).
  - Probe OVS↔OVS: ethertype `0x88B5` mỗi 0,5 s cả hai chiều, chết sau 2,0 s.
  - OVS↔Core (IOL không chạy OpenFlow): ARP tới SVI Core mỗi 1 s, chết sau 3,5 s.
  - Chế độ `admin` (PortMod down): OVS báo PortStatus ngay → phát hiện ~10 ms.
- **converge** = mốc phát hiện → **barrier reply** của mọi switch bị ảnh hưởng (hạn chờ 1 s; switch im lặng ghi ở `unanswered`).
- **Mất gói dữ liệu** = ping liên tục từ controller tới host sau Access (gửi đều theo chu kỳ, mất = không trả lời sau 1 s).
- Sau mỗi lần cây đổi, controller phát **RARP thay cho host** đi theo đường mới để Core-SW1/2 (switch truyền thống) học lại vị trí MAC ngay – thiếu bước này dữ liệu mất ~11–12 s.

Chạy bộ thử tự động (ghi `log/sdn-eval/`): `.claude/skills/campus-network-lab/scripts/lab/sdn_recovery_test.py`

## Kết quả đo 04/10/2026 (host 1, ping 0,1 s tới PC-HanhChinh-S100)

| Liên kết | Kiểu | detect | converge | Mất gói khi cắt | Khi khôi phục |
|---|---|---|---|---|---|
| A4-D1 (Access–Dist) | silent | 1 762 ms | 8,7 ms | 18 gói / 1,81 s | 0 |
| A4-D1 | admin | 11 ms | 6,2 ms | 0 | 3 gói / 0,30 s |
| D1-C1 (Dist–Core) | silent | 2 918 ms | 8,7 ms | 29 gói / 2,92 s | 3 gói / 0,30 s |
| D1-C1 | admin | 13 ms | 8,5 ms | 3 gói / 0,30 s | 1 gói / 0,10 s |
| Tắt hẳn Dist-SW1 (node 5) | – | ~2 s (probe) | – | 19 gói / 1,9 s | 0 |

Gián đoạn dữ liệu ≈ thời gian phát hiện; phần hội tụ của controller < 10 ms. Rút ngắn chu kỳ probe sẽ giảm gián đoạn khi đứt ngầm nhưng tăng nguy cơ báo nhầm.

## Kết quả đo mục tiêu 1 – thêm VLAN / khu vực mạng (04/10/2026)

Kịch bản: thêm VLAN 50 "Phong Lab" (10.1.50.0/24) cho cổng `Access-SW1.ens7` (VPC19) – `scripts/lab/sdn_vlan_test.py`.

| Phần | Cách làm | Thời gian | Số thiết bị / lệnh |
|---|---|---|---|
| Campus SDN (6 OVS) | 1 lệnh API `POST /campus/vlan` | **3,8 ms** tới barrier (xoá: 3,6 ms) | 1 OVS bị ảnh hưởng, 1 flow-mod |
| Core-SW1 (IOL) | CLI 18 lệnh (máy gõ qua console) | 35,4 s (xoá 27,9 s) | 1 thiết bị |
| Core-SW2 (IOL) | CLI 18 lệnh | 36,3 s (xoá 27,0 s) | 1 thiết bị |
| Kiểm chứng | VPC19 IP 10.1.50.100 | ping gateway VRRP 3/3, DHCP-Server 3/3 | – |

Nếu toàn bộ campus là switch truyền thống: thêm 2 Dist + các Access (VLAN, trunk allowed trên mọi trunk, cổng access) – SDN gói phần này vào 1 lệnh API, giữ lại phần L3 trên Core. Còn tay: scope DHCP trên DHCP-Server 72.

**Lưu ý IOL:** xoá VLAN khi Core đang là VRRP Master bằng `no interface VlanX` gửi dồn đã làm Core-SW1 IOL crash (04/10/2026, tự lên lại sau khi start node 3; cây SDN tự phục hồi). Đoạn xoá do controller sinh nay theo thứ tự an toàn: `no vrrp` → `shutdown` → OSPF → trunk → `no interface` → `no vlan`.

## Pipeline OpenFlow (từ giai đoạn 3)

| Bảng | Ưu tiên | Nội dung |
|---|---|---|
| 0 | 65500 / 65000 | mô phỏng cắt liên kết / probe + ARP probe → controller |
| 0 | 60000 | VLAN 99 tĩnh có hướng (Dist) |
| 0 | 45000 | flow cố định quản trị của Access (`0xba5f`, script restore) |
| 0 | 40000 | chặn cạnh ngoài cây (VLAN có tag) |
| 0 | 20001–20999 | **chính sách**: deny → drop, allow → goto bảng 1 (chỉ trên 4 Access) |
| 0 | 0 | goto bảng 1 |
| 1 | 1 | unicast đã học (idle 300 s) |
| 1 | 0 | table-miss → controller (L2 reactive) |

## Kết quả đo mục tiêu 5 – chính sách tập trung (04/10/2026)

Kịch bản `scripts/lab/sdn_policy_test.py`: luật deny ICMP hai chiều VLAN 10 ↔ VLAN 40, kiểm bằng VPC19 (10.1.10.100) → PC-HanhChinh-S100 (10.1.40.102).

| Bước | Kết quả |
|---|---|
| Áp luật (1 lệnh API) | **8,0 ms** tới barrier của 4 Access (12 flow-mod) |
| Khi luật đang áp | 10.1.40.102 **0/3**; gateway 10.1.10.1 và DHCP-Server 10.1.90.10 vẫn 3/3 |
| Bộ đếm luật | 3 gói khớp |
| Xoá luật | **5,2 ms**, thông lại 3/3 |

Truyền thống tương đương: ACL trên SVI 2 Core (hoặc VACL từng switch) – mỗi luật × mỗi thiết bị nhiều lệnh CLI, không có bộ đếm tập trung.

## Kết quả đo mục tiêu 4 – tải Core / Distribution (04/10/2026)

`scripts/lab/sdn_load_test.py` – 3 pha × 60 s, mẫu 5 s (trung bình):

| Chỉ số | Nền | Có lưu lượng | Lưu lượng + cắt D1-C1 |
|---|---|---|---|
| Dist-SW1 Mbps / pps | 1,10 / 848 | 2,72 / 1 062 | 1,19 / 916 |
| Dist-SW2 Mbps / pps | 3,20 / 2 443 | 3,19 / 2 458 | 3,29 / 2 584 |
| Uplink Core-SW1 Mbps / pps | 0,67 / 466 | 1,48 / 575 | 0,72 / 523 |
| Packet-in/s tổng | 92,9 | 93,8 | 95,6 |
| CPU node 9 / Ryu | 8,8 % / 5,0 % | 6,3 % / 5,7 % | 9,6 % / 5,6 % |

- Tải điều khiển ổn định, **không phụ thuộc lưu lượng người dùng** (luồng đã học đi thẳng bằng flow, không qua controller). Packet-in nền chủ yếu: probe liên kết (~40/s), LLDP/BDDP của ONOS (chạy song song cổng 6654), ARP/broadcast.
- Dist-SW2 tải cao nhất vì gánh toàn bộ VLAN 99 (Access ↔ controller đi qua nó).
- Hạn chế: VPCS chỉ sinh vài trăm kbit/s nên chưa thử được tải cao.
- CPU Core qua SNMP v2c RO (ACL 98 chỉ cho 10.1.99.10; community trong `state/snmp.json` 0600, không commit). NOC dò lần lượt `cpmCPUTotal5secRev`/`cpmCPUTotal5sec` (GETNEXT) rồi `busyPer`/`avgBusy1`. **Core-SW1 đọc được; Core-SW2 timeout** vì Vlan99 của nó là “ốc đảo” (chỉ có Et1/2 → Dist-SW1 ens10, OVS chặn VLAN 99 ở đó) nên gói trả lời không về được controller – xem mục SPOF bên dưới.

## Đường quản trị VLAN 99 là điểm lỗi đơn (SPOF)

Controller → Core-SW1 → **D2-C1** → Dist-SW2 → (inter-dist, 4 Access). Cắt D2-C1 thì Dist-SW2, 4 Access mất controller sau ~9 s (Dist-SW1 vẫn còn) – **đúng theo thiết kế hiện tại**, dữ liệu vẫn chạy bằng flow đã cài (`fail_mode=secure`). Đã sửa các lỗi khiến lab kẹt (04/10/2026):

- Cắt thử silent có `hard_timeout` → OVS tự gỡ dù controller không tới được (trước đây flow drop nằm vĩnh viễn, phải gỡ tay qua VNC).
- Nhiều OVS cùng im lặng (> 1 s) = mất kênh điều khiển, **không** kết luận link chết → không chặn cổng Access trên Dist-SW1 (trước đây đánh dấu 11/13 link down sau 1,6 s). Một switch im lặng (switch chết) vẫn chuyển mạch nhanh như cũ.
- `mode=admin` (PortMod) trên cổng thuộc đường VLAN 99 bị từ chối vì không thể bật lại từ xa.

Kiểm chứng: cắt D2-C1 30 s → 0 link_down giả, OVS tự gỡ flow ở giây 30, 6/6 switch nối lại ở giây 32, 13/13 link sau ~34 s; hồi quy A1-D1 1,8 s / D1-C1 3,0 s như trước.
Muốn bỏ SPOF cần đường VLAN 99 thứ hai (vd cho VLAN 99 qua Core-SW1 Et0/2 hoặc Core-SW2 Et1/2 → Dist-SW1) – thay đổi topology, chưa làm.

## Kết quả đo mục tiêu 3 – hiệu năng giữa các VLAN (04/10/2026)

`scripts/lab/sdn_perf_test.py --count 5`: VPC14 (V10), VPC20/21 (V20), VPC15/16 (V30), VPC17 + PC-HanhChinh (V40), các nguồn chạy song song, 36 cặp trong 54 s.

| | Cặp | RTT trung bình | Jitter | Mất gói |
|---|---|---|---|---|
| Trong VLAN (L2 qua OVS) | 5 | **1,57 ms** | 1,27 ms | 0 % |
| Khác VLAN (định tuyến qua Core-SW1) | 31 | **2,91 ms** | 1,19 ms | 0 % |

## Bảo mật

REST 8080 (kể cả `ofctl_rest` sửa được flow) và ONOS 8181/8101 **không xác thực**. Trên `ens6` (LAN thật) đã chặn bằng chain iptables `CAMPUS_ENS6` trong `SDN_CONTROLLER-autostart.sh`: chỉ host EVE (`CAMPUS_ADMIN_SRC`, mặc định 10.215.28.26), DHCP và ping được vào. `ens3` (VLAN 99: OVS, PC-Management) không bị ảnh hưởng.
