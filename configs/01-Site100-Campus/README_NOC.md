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
| Sức khoẻ (10/10) | Kênh điều khiển từng switch: kết nối / im lặng (ms) / **đóng băng**, cha trong cây dữ liệu, **đường quản trị VLAN 99 đang dùng** (chính qua Dist-SW2 hay dự phòng qua Dist-SW1), số lần nối lại 1 h, bản tin bị bỏ; **controller khựng** (biểu đồ 1 h) + CPU node 9; **role STP VLAN 99 của Core-SW1** (Et1/2 designated, Et0/2 backup) qua SNMP; danh sách cảnh báo tự sinh | 2 |
| Kịch bản (10/10) | Chọn S1–S6 → chạy tự động (kiểm tra mạng ổn định → cắt silent → giữ → khôi phục → chờ 13/13 + 6/6), ping 0,1 s tới 1 máy mỗi VLAN, kết luận **ĐẠT/KHÔNG ĐẠT** (gián đoạn khi cắt ≤ 5 s, khi khôi phục ≤ 3 s, mạng về đầy đủ); hiển thị chung kết quả **cắt thật** do `sdn_realcut_test.py` đẩy lên | 2 |

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
| `GET /campus/health` | Sức khoẻ: `switches[]` (connected, control_ok, last_rx_ms, frozen, parent, mgmt_path, reconnects_1h, send_dropped), `controller` (stalls_1h, stall_max_ms_1h, stall_log), `stp.ports[]` (port, role, expect), `issues[]` |
| `GET /campus/scenario` | Định nghĩa S1–S6, trạng thái đang chạy (`step`, `log`), `results[]` (lưu `metrics/scenarios.json`, 50 bản) |
| `POST /campus/scenario` | `{"action":"run","ids":["S1","S5"],"hold":15,"gap":15,"targets":["10.1.40.102"]}`, `{"action":"stop"}`, `{"action":"clear"}` |
| `POST /campus/scenario/result` | Kết quả cắt thật từ script lab (cùng định dạng, `kind:"cat that"`) |

## Cách đo (mục tiêu 2 – thời gian khôi phục)

- **detect** = mốc phát hiện − mốc kích hoạt (lúc bấm mô phỏng, hoặc lần cuối thấy probe).
  - Probe OVS↔OVS: ethertype `0x88B5` mỗi 0,5 s cả hai chiều, chết sau 2,0 s.
  - OVS↔Core (IOL không chạy OpenFlow): ARP tới SVI Core mỗi 1 s, chết sau 3,5 s.
  - Chế độ `admin` (PortMod down): OVS báo PortStatus ngay → phát hiện ~10 ms.
- **converge** = mốc phát hiện → **barrier reply** của mọi switch bị ảnh hưởng (hạn chờ 1 s; switch im lặng ghi ở `unanswered`).
- **Mất gói dữ liệu** = ping liên tục từ controller tới host sau Access (gửi đều theo chu kỳ, mất = không trả lời sau 1 s).
- Sau mỗi lần cây đổi, controller phát **RARP thay cho host** đi theo đường mới để Core-SW1/2 (switch truyền thống) học lại vị trí MAC ngay – thiếu bước này dữ liệu mất ~11–12 s.

Chạy bộ thử tự động (ghi `log/sdn-eval/`): `.claude/skills/campus-network-lab/scripts/lab/sdn_recovery_test.py`

Cắt **thật** (hạ tap trên host 1) và đẩy kết quả lên tab Kịch bản: `.claude/skills/campus-network-lab/scripts/lab/sdn_realcut_test.py --cases A4-D1,D1-C1,D2-C1,A4-D1+D2-C1` (hoặc `--node 8 --node-hold 60` để tắt hẳn một OVS). Tap = `vunl6_<node>_<N-3>` với cổng `ensN`.

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
- CPU Core qua SNMP v2c RO (ACL 98 chỉ cho 10.1.99.10; community trong `state/snmp.json` 0600, không commit). NOC dò lần lượt `cpmCPUTotal5secRev`/`cpmCPUTotal5sec` (GETNEXT) rồi `busyPer`/`avgBusy1`. Đích: Core-SW1 `10.1.99.1`, Core-SW2 `10.1.90.3` (Vlan99 của Core-SW2 đã tắt, về 10.1.99.0/24 bằng static route qua Po10) – **cả hai đọc được** (04/10/2026).

## Đường quản trị VLAN 99 có dự phòng (04/10/2026)

> **Đã thay bằng thiết kế 10/10/2026** (mục “VLAN 99 không phụ thuộc STP” bên dưới). Phần này giữ để đối chiếu.

Trước đây: Controller → Core-SW1 Et1/2 → **D2-C1** → Dist-SW2 → (inter-dist, 4 Access) là đường duy nhất (SPOF): cắt D2-C1 thì Dist-SW2 + 4 Access mất controller, kèm 3 lỗi khiến lab kẹt (cắt thử không tự gỡ, mất kênh điều khiển bị coi là link chết, admin-cut không bật lại được).

Bây giờ:

| Thành phần | Thay đổi |
|---|---|
| Core-SW1 | Et0/2 (→ Dist-SW1 ens9) mang thêm VLAN 99; `spanning-tree vlan 99 hello-time 1 / forward-time 4 / max-age 6`. Vòng duy nhất Et1/2 ↔ OVS ↔ Et0/2 do rapid-PVST chặn: Et0/2 = **Back BLK** (BPDU đi xuyên OVS) |
| OVS (`MGMT_FLOWS`) | Dist-SW1 bắc cầu ens8 ↔ ens9 ↔ patch-mgmt **và ens9 ↔ 4 cổng Access** (09/10); Dist-SW2: ens10 ↔ Access, Access → chỉ ens10 + patch (không vào inter-dist), inter-dist không xuống Access. Bên trong OVS vẫn là cây, mỗi Access nhận đúng 1 bản sao từ mỗi cổng Core (unit test `test_mgmt_vlan99_loop_free`). Bình thường Et0/2 bị STP chặn nên Access đi qua Dist-SW2; Dist-SW2 chết/D2-C1 đứt → Et0/2 mở → Access đi qua Dist-SW1 |
| Core-SW2 | **Không** vào VLAN 99: OVS flood tĩnh (không học MAC) + 2 router cùng VLAN ⇒ mỗi router định tuyến ngược unicast của router kia ⇒ bão ~40 000 pps (đã gặp khi thử, gỡ ngay). Vlan99 tắt, static route `10.1.99.0/24 → 10.1.0.5` |
| App | Cắt thử: OVS↔OVS = flow drop `hard_timeout`; OVS↔Core = PortMod `NO_RECV|NO_FWD` (chặn 2 chiều – drop 1 chiều làm Et0/2 mở trong khi Et1/2 vẫn nhận ⇒ vòng). Hết `max_s` controller tự bật lại cổng. Nhiều OVS cùng im lặng > 1 s = mất kênh điều khiển, không kết luận link chết. Admin-cut chỉ còn bị từ chối trên cổng Access ↔ Dist-SW2 |
| Ryu | Gửi bản tin chờ tối đa 0,5 s (`SEND_WAIT`) thay vì treo vô hạn khi kết nối chết làm đầy hàng đợi 16 bản tin (lỗi Ryu 4.34 làm vòng probe đứng hẳn); echo 2 s × 3 (`CONF.set_override`, `ryu-manager` trên node 9 không nhận cờ dòng lệnh) |

Kiểm chứng (`sdn_recovery_test.py --links D2-C1 --modes silent,admin --hold 40`): OVS mất controller ~2,5 s (giây 9,3 → 11,9, lúc STP mở Et0/2) rồi tự nối lại qua Dist-SW1; 13/13 link; ping PC-HanhChinh mất 4 gói (0,4 s) mỗi lần cắt. Hạn chế còn lại: khi khôi phục sau cắt `silent`, kênh điều khiển gián đoạn thêm ~2–10 s (RSTP *dispute*: Et1/2 nhận BPDU designated của Et0/2 → tự chuyển discarding, cả 2 cổng cùng chặn tới khi hết forward-delay; bộ đếm `transitions to forwarding` Et1/2 = 16 sau 09/10). Access chỉ chuyển sang Dist-SW1 khi STP mở Et0/2 (Dist-SW2 chết hoặc D2-C1 đứt); đứt riêng A*-D2 thì Access đó mất controller (dữ liệu vẫn chạy nhờ “đóng băng”).

## VLAN 99 không phụ thuộc STP (10/10/2026)

Gốc lỗi S4/S5: OVS nối Core-SW1 Et1/2 → Dist-SW2 → inter-dist → Dist-SW1 → Et0/2 trong VLAN 99 nên Core nghe chính BPDU của nó (Et0/2 = Back BLK). Đứt D2-C1 phải chờ STP mở Et0/2 (~10 s); khôi phục thì Et1/2 bị **Dispute** ~8 s (không có bắt tay proposal/agreement với chính mình) ⇒ 6 OVS mất controller.

Thiết kế mới (`MGMT_RULES` trong `campus_switch_13.py`, chỉ đổi flow do controller cài – **không sửa Core-SW1, không sửa script OVS**):

| Quy tắc | Nội dung |
|---|---|
| Không vòng qua Core | Khung vào từ cổng Core của một Dist **không bao giờ** ra cổng Core nào ⇒ Core không nghe BPDU của mình ⇒ **Et1/2 và Et0/2 đều Desg FWD**; STP chỉ còn là lưới an toàn |
| Đi lên | patch / cổng Access của Dist → cổng Core của nó **và** inter-dist “đi lên” (Dist kia chỉ đưa ra cổng Core của nó). Access gửi lên cả 2 uplink (0xba5f) ⇒ mỗi Access có tới 4 đường, mỗi Dist 2 đường – không cần STP hay controller chuyển mạch |
| Đi xuống | Core → Access + patch + inter-dist “đi xuống” (Dist kia chỉ đưa vào patch + Access) |
| Mã VLAN inter-dist bất đối xứng | Dist-SW1→Dist-SW2: 99 = đi lên; Dist-SW2→Dist-SW1: 99 = đi xuống (đúng như bootstrap 0xba5e và flow bản cũ); Dist-SW2 nhờ đi lên = 3999; Dist-SW1 gửi xuống = 3998. Lần thử đầu dùng nghĩa đối xứng ⇒ Dist-SW1 (còn flow cũ / vừa khởi động lại) **không nối lại được** – có test `test_mgmt_vlan99_bootstrap_compatible` |
| Chống phản xạ | Core flood ARP… của một OVS ra cổng Core còn lại ⇒ khung về lại chính OVS đó (br-mgmt học sai MAC, từng mất controller ~20 s). Flow `0x5d04` priority 60500 trên cổng Core của Dist drop khung có `eth_src` = MAC quản trị của 6 OVS (lấy từ `/proc/net/arp` của node 9, cập nhật 2 s) |

Unit test: mô phỏng khung qua Dist/Access/Core (Core flood): không vòng, Core không nhận lại khung của chính nó, không phản xạ, mọi OVS vẫn tới Core khi mất **bất kỳ** 1 liên kết hoặc 1 Dist, ca kép A4-D1 + D2-C1, Dist ở bootstrap / flow cũ. Live sau deploy: Et0/2 + Et1/2 Desg FWD, 6 flow chống phản xạ, ~100–170 pps trên Et0/2/Et1/2 (không bão).

Kết quả (10/10/2026, sau khi tắt ONOS + VLAN 99 mới):

| Kịch bản (mô phỏng silent, giữ 15 s) | Gián đoạn khi cắt | Khi khôi phục | Về 13/13 + 6/6 | Trước (sáng 10/10) |
|---|---|---|---|---|
| S1 D1-C1 | 3,3 s | 0,3 s | 1,5 s | ĐẠT (2,8 / 0,5 s) |
| S2 A4-D1 | 2,1 s (VLAN 40) | 0 | 1,5 s | ĐẠT |
| S3 D1-D2 | **0** | 0 | 1,5 s | ĐẠT (0,9 s, Dist-SW1 mất controller) |
| S4 D2-C1 | **0** | **0** | 2,0 s | KHÔNG ĐẠT (10,9 s khi khôi phục) |
| S5 A4-D1 + D2-C1 | **3,4 s** (VLAN 40) | **0** | 2,0 s | KHÔNG ĐẠT (15 s + 10,3 s) |
| S6 D1-C1 + D1-C2 | 3,5 s | 0,3 s | 1,5 s | ĐẠT |

**6/6 ĐẠT**, không switch nào mất controller trong cả loạt. Cắt **thật** (hạ tap, giữ 20 s, `sdn_realcut_test.py`): D2-C1 **0 gói**; A4-D1 + D2-C1 VLAN 40 mất 3,2 s (Access-SW4 chuyển sang Dist-SW2), khôi phục 0,2 s; D1-C1 mất 2,8–3,1 s, khôi phục ≤ 0,4 s – cả 3 ĐẠT. Vẫn còn khựng controller hiếm (đo được 4,9 s một lần sau loạt cắt thật) dù đã tắt ONOS – nghi CPU host, ân hạn `controller_stall` giữ không báo link chết giả.

## Kiểm thử cold-start + cắt link thật 09/10/2026

Cắt **thật** = `ip link set vunl6_<node>_<if> down` trên host 1 (VM không biết, giống rút dây). Ping 0,1 s từ controller tới 4 VLAN (`10.1.40.102`, `10.1.10.100`, `10.1.20.100`, `10.1.30.100`).

| Ca | Trước sửa (app 04/10) | Sau sửa (09/10) |
|---|---|---|
| Đứt A4-D1 | VLAN 40 mất 1,8 s | 1,8 s |
| Đứt cùng lúc 4 uplink A*-D1 | 4 VLAN mất 2,0 s | 1,9 s |
| Đứt D1-C1 | 4 VLAN mất 2,8 s | 2,7–4,5 s (phụ thuộc controller khựng) |
| Đứt D2-C1 (đường quản trị chính) | dữ liệu ≈ 0, **6 switch mất controller ~2,5 s** | như cũ |
| Đứt A4-D1 + D2-C1 | VLAN 40 mất 13,8 s; **sau khôi phục kẹt 9/13 link, Dist-SW2 mất controller vĩnh viễn** | VLAN 40 mất ~24 s (controller mù tới khi STP mở Et0/2), **tự về 13/13** |
| Tắt hẳn Dist-SW2 (node 8) | **4 VLAN mất 100% ~3,5 phút** (controller chặn cổng Dist-SW1 xuống Access) | **0–5 gói**; 4 Access nối lại qua Dist-SW1 sau ~11 s; bật lại: 0 gói |

Lỗi đã sửa trong `campus_switch_13.py` (unit test 27/27):
1. **Access mất controller ≠ Access chết**: `compute_data_tree(..., frozen)` giữ Access mất kết nối làm lá trên link cha cũ (OVS `secure` vẫn giữ flow cây cũ). Console vẽ viền vàng nét đứt + dấu `*`.
2. **Access có đường quản trị dự phòng qua Dist-SW1** (MGMT_FLOWS ở trên).
3. **Guard VLAN 99 không bao giờ bị xoá trước khi cài** (ghi đè bằng `OFPFC_ADD`): trước đây xoá rồi cài lại, kết nối đứt giữa chừng ⇒ switch mất đường VLAN 99 vĩnh viễn. Bootstrap `0xba5e` chỉ bị xoá khi không có bản tin nào bị rơi.
4. **Controller khựng ⇒ ân hạn** `CORE_TIMEOUT` (sự kiện `controller_stall`, tab Sức khoẻ): sau khi khựng, switch gửi gói đầu tiên không còn bị coi là im lặng nên link Core của nó bị báo chết giả (cold-start: 4 link Core “chết” cùng một giây).

Cold-start toàn Site 100 (bật 19 node cùng lúc): Access-SW2 rơi vào **emergency mode** (CPU stall ~40 s lúc boot → `/boot` timeout trong `fstab`) ⇒ OVS không chạy. Đã thêm `nofail,x-systemd.device-timeout=30s` cho `/boot` (bản cũ `/etc/fstab.orig`) trên **cả 6 OVS và node 9** (10/10). VPC xin DHCP trước khi DHCP-Server/OVS sẵn sàng ⇒ phải `ip dhcp` lại.

### Nguyên nhân controller khựng: ONOS chạy song song (10/10/2026)

Từ 14:20 tới 19:50 ngày 09/10, controller khựng **theo cụm mỗi 5–15 phút**, mỗi lần 0,5–9,1 s; vài cụm làm cả 6 OVS mất kết nối rồi nối lại. Ghi `/proc/<pid>/stat` mỗi 0,5 s trên node 9 (2 vCPU) trong một cụm: CPU rảnh của VM về **0 suốt ~18 s**, `java` (ONOS 2.7) chiếm 60–155 tick/0,5 s (> 1 vCPU), Ryu chỉ còn 5–50 tick. Mở đầu cụm có một lần cả VM đứng 2,8 s (steal + sys tăng). Tích luỹ 5,5 h: java 51 phút CPU, Ryu 26 phút.

Xử lý (người dùng cho phép tắt ONOS): `systemctl disable --now onos` và `CPUShares=8192` cho `campus-ryu.service` (drop-in `set-property`, giữ qua reboot). Sau đó RAM VM dùng còn 179 MB (trước ~1,3 GB). Kết quả sau khi tắt ONOS: xem bảng kịch bản dưới. 6 OVS vẫn khai báo controller thứ hai `tcp:10.1.99.10:6654` (ONOS) trong script restore – OVS chỉ thử nối lại định kỳ, vô hại; bỏ khi chắc không dùng ONOS nữa.

### Tab Kịch bản – lần chạy đầu sau khi tắt ONOS (10/10/2026, mô phỏng silent, giữ 15 s, ping 0,1 s tới 4 VLAN)

| Kịch bản | Gián đoạn dài nhất khi cắt | Khi khôi phục | Về 13/13 + 6/6 sau | Kết quả |
|---|---|---|---|---|
| S1 D1-C1 (uplink gốc) | 2,8 s (4 VLAN, phát hiện 2,8 s, hội tụ 11,5 ms) | 0,5 s | 12,5 s | ĐẠT |
| S2 A4-D1 | 2,3 s (chỉ VLAN 40) | 0,1 s | 1,5 s | ĐẠT |
| S3 D1-D2 | 0,9 s (Dist-SW1 mất controller ~1 s vì đường quản trị đi qua inter-dist; 4 Access chuyển sang Dist-SW2) | 0,1 s | 4,0 s | ĐẠT |
| S4 D2-C1 (đường quản trị chính) | 0,5 s | **10,3–10,9 s (4 VLAN)** | 12,5 s | KHÔNG ĐẠT |
| S5 A4-D1 + D2-C1 | **15 s VLAN 40** (controller mù, không chuyển được Access-SW4) | **10,3 s** | 12,5 s | KHÔNG ĐẠT |
| S6 D1-C1 + D1-C2 | 3,2 s | 0,4 s | 11,5 s | ĐẠT |

Nguyên nhân S4/S5 (đã bắt `show spanning-tree vlan 99` trên Core-SW1 mỗi 2,5 s trong lúc chạy lại S4): khi cắt, Et0/2 đi `Back BLK → Desg BLK → LRN → FWD` (~10 s, đường dự phòng mở). Khi khôi phục, Et0/2 về `Back BLK` ngay nhưng **Et1/2 rơi vào `Desg BLK … Dispute` → `LRN` → `FWD` mất ~8 s**: Et1/2 nhận BPDU designated/forwarding của chính Et0/2 vòng qua OVS (sw5.ens9 → ens8 → sw8.ens10), và vì "hàng xóm" là chính nó nên không có bắt tay proposal/agreement → phải chờ 2 × forward-delay. Trong ~8 s đó VLAN 99 mất ở cả 2 cổng ⇒ 6 OVS mất controller. VLAN 10 (dữ liệu) trên Core vẫn FWD suốt — phần mất ping có thể một phần do chính controller (nguồn ping) bị cô lập, cần đo thêm từ VPC để tách bạch. Hướng sửa: bỏ phụ thuộc STP cho VLAN 99 (OVS không chuyển BPDU giữa 2 cổng Core, controller tự chọn 1 đường quản trị + rapid-PVST chỉ làm lưới an toàn) – chưa làm.

## Kết quả đo mục tiêu 3 – hiệu năng giữa các VLAN (04/10/2026)

`scripts/lab/sdn_perf_test.py --count 5`: VPC14 (V10), VPC20/21 (V20), VPC15/16 (V30), VPC17 + PC-HanhChinh (V40), các nguồn chạy song song, 36 cặp trong 54 s.

| | Cặp | RTT trung bình | Jitter | Mất gói |
|---|---|---|---|---|
| Trong VLAN (L2 qua OVS) | 5 | **1,57 ms** | 1,27 ms | 0 % |
| Khác VLAN (định tuyến qua Core-SW1) | 31 | **2,91 ms** | 1,19 ms | 0 % |

## Bảo mật

REST 8080 (kể cả `ofctl_rest` sửa được flow) và ONOS 8181/8101 **không xác thực**. Trên `ens6` (LAN thật) đã chặn bằng chain iptables `CAMPUS_ENS6` trong `SDN_CONTROLLER-autostart.sh`: chỉ host EVE (`CAMPUS_ADMIN_SRC`, mặc định 10.215.28.26), DHCP và ping được vào. `ens3` (VLAN 99: OVS, PC-Management) không bị ảnh hưởng.
