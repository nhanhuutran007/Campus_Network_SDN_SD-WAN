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
| Chính sách / Tải thiết bị / Hiệu năng | các giai đoạn 3–5 | 5, 4, 3 |

## REST

| Endpoint | Ý nghĩa |
|---|---|
| `GET /noc/summary` | Tổng hợp (switch, liên kết, gốc cây, hội tụ gần nhất/trung bình, BW) |
| `GET /noc/switches`, `/noc/ports`, `/noc/congestion`, `/noc/history` | như phiên bản 1 (PortStats nay được poll định kỳ 5 s) |
| `GET /campus/topology` | Đồ thị: nút, liên kết (`up`, `in_tree`, tuổi probe), cổng bị chặn, VLAN, tham số thăm dò |
| `GET /campus/events?since=N` | Sự kiện: `link_down/up`, `switch_down/up`, `tree_change`, `test_inject/restore` kèm `detect_ms`, `converge_ms`, `total_ms`, `switches`, `flow_mods`, `announced`, `unanswered` |
| `POST /campus/linktest` | `{"link":"A1-D1","action":"down|up","mode":"silent|admin"}` |
| `GET /campus/vlans` | VLAN, cổng access, cổng trống trên Access |
| `POST /campus/vlan` | `{"action":"add|ports|delete","vid":50,"name":"Phong Lab","ports":["Access-SW1.ens7"]}` → sự kiện `vlan_*` (thời gian tới barrier) + `core_config` (IOS cho Core-SW1/2) |
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

## Bảo mật

REST 8080 (kể cả `ofctl_rest` sửa được flow) và ONOS 8181 đang nghe trên `ens6` (LAN thật) **không xác thực** – nên chặn bằng firewall node 9, chỉ mở cho host 1/PC quản trị.
