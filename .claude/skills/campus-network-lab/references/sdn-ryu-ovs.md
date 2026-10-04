# SDN Site 100: Ryu + OVS

Đọc lại các file nguồn trong `configs/01-Site100-Campus/` trước khi hành động — chúng đang được sửa (xem `project-status.md`). Tài liệu này giải thích cơ chế và bài học; con số cụ thể (port, env) lấy từ file, không từ trí nhớ.

## Mục lục
- Mapping
- Thiết kế đang dùng
- Trạng thái nào còn sau stop/start
- VLAN 99: vòng lặp và "cây" quản trị
- Chẩn đoán DHCP theo lớp + 3 root cause đã sửa
- Khôi phục OVS
- Triển khai qua console (không SSH)
- Cạm bẫy Ryu/OVS

## Mapping

| Node | Thiết bị | IP mgmt (VLAN 99) | DPID | Ghi chú cổng |
|---:|---|---|---|---|
| 9 | SDN_CONTROLLER | `10.1.99.10/24` (`ens3`) | — | `e0`→Farm E1/0 (access 99); `ens6`/e3 = Cloud-NAT (Internet cho pip, KHÔNG phải control plane) |
| 5 | Dist-SW1 | `.11` | `0…05` | ens4–7 → Access-SW1–4; ens8 inter-dist; ens9 → Core-SW1 Et0/2; ens10 → Core-SW2 Et1/2 |
| 8 | Dist-SW2 | `.12` | `0…08` | ens4–7 → Access-SW1–4; ens8 inter-dist; ens9 → Core-SW2 Et0/2; ens10 → Core-SW1 Et1/2 |
| 68 | Access-SW1 | `.21` | `0…44` | ens4/ens5 uplink (dual-home Dist-SW1/2); ens6/7 access VLAN 10 (VPC14, 19) |
| 66 | Access-SW2 | `.22` | `0…42` | access VLAN 20 (VPC20, 21) |
| 70 | Access-SW3 | `.23` | `0…46` | access VLAN 30 (VPC15, 16) |
| 69 | Access-SW4 | `.24` | `0…45` | access VLAN 40 (VPC17, 18) |

Tap trên host EVE = `vunl6_<node>_<iface-index>` (iface-index của `.unl`, KHÔNG phải network-id): node 5/8 e1..e4=ens4..7, e5=ens8, e6=ens9, e7=ens10. Core-SW1 (node 3): Et1/1=iface 17 (↔Farm E0/0), Et0/2=32, Et1/2=33; Core-SW2 (node 4) tương tự; Farm (24): 24_17=DHCP-Server, 24_0=Core-SW1, 24_1=controller.

Frame MAC `00:50:06:00:NN:0X` trên tap switch là **dhclient của chính VM Ubuntu OVS**, không phải VPC.

## Thiết kế đang dùng (app v2, triển khai 04/10/2026)

- **App** `campus_switch_13.py` v2 (bản v1 lưu trong VM ở `/root/ryu-app/campus_switch_13.py.v1`, md5 `8d4b2e53…`). Phạm vi: **chỉ campus chính Site 100**; liên site do SD-WAN lo.
  - **Cây dữ liệu tính tập trung**: `LINKS` (13 liên kết tĩnh: D*-C*, D1-D2, A*-D1/D2, có trọng số) + trạng thái sống/chết thật → Dijkstra từ Core-SW1 (dự phòng Core-SW2). Cạnh ngoài cây: flow DROP `priority=100` (`vlan_vid` có tag, cookie `0x5d02`). Đổi cây: **chặn trước, mở sau**; xoá flow unicast đã học (cookie 0) trên **mọi** switch. Hàm thuần `compute_data_tree` có test.
  - **Thăm dò chủ động** (EVE: link/node chết KHÔNG làm cổng bên kia đổi trạng thái, VM tắt cứng KHÔNG đóng TCP → Ryu không thấy DEAD): probe ethertype `0x88B5` mỗi 0,5 s hai chiều (chết sau 2,0 s), ARP tới SVI Core mỗi 1 s với MAC nguồn riêng từng liên kết `02:5d:00:00:01:xx` (chết sau 3,5 s); `UP_HOLD` 1 s chống dao động. PortStatus vẫn dùng (phát hiện ~10 ms khi cổng down).
  - **VLAN 99 tĩnh, có hướng, không phụ thuộc cây** (`MGMT_FLOWS`, `priority=60000`, cookie `0x5d01`): Access ↔ controller **đi thẳng qua Dist-SW2** (Access `ens5` → sw8 → `ens10`); Dist-SW1 ↔ controller qua inter-dist; bản sao vào Dist-SW1 bị bỏ. **Không flood tự do**: Access gửi 99 lên cả 2 uplink (`0xba5f`), flood sẽ phản xạ khung về chính Access → `br-mgmt` học sai MAC của nó → controller mất Access ~20 s mỗi lần (đã gặp 03/10). Hệ quả tốt: Dist-SW1 chết thì Access vẫn nối controller. Phụ thuộc: Dist-SW2 + `D2-C1` = **SPOF quản trị**: cắt D2-C1 thì Dist-SW2 + 4 Access mất controller sau ~9 s (Dist-SW1 còn), dữ liệu chạy bằng flow cũ. Từ 04/10 app chịu được: cắt thử silent có `hard_timeout` (`max_s`, mặc định 60 s) nên OVS tự gỡ; nhiều OVS cùng im lặng > `CONTROL_SILENT` 1 s ⇒ coi là mất kênh điều khiển, `_eval_link` trả None (không chặn cây); admin PortMod trên cổng `MGMT_CRITICAL` bị từ chối. Nếu vẫn kẹt flow cắt cũ: VNC vào OVS `ovs-ofctl -O OpenFlow13 del-flows br0 cookie=0x5d03/-1`.
  - **RARP thay host sau mỗi lần cây đổi** (host học ở cổng access, đi theo uplink MỚI): Core-SW1/2 là switch truyền thống, bảng MAC giữ nhánh cũ → thiếu bước này dữ liệu mất 11–12 s.
  - **Đo hội tụ**: mốc phát hiện → barrier reply mọi switch bị ảnh hưởng (hạn 1 s, switch im lặng ghi `unanswered`); sự kiện + CSV `/root/ryu-app/metrics/events.csv`.
  - Kết nối switch: cài guard trước, xoá flow cookie 0 (gồm flow cũ của v1), rồi cây; Dist xoá bootstrap `0xba5e`. PortDesc thứ hai cùng kết nối (do NOC yêu cầu) bị bỏ qua.
  - **Cạm bẫy Ryu**: KHÔNG đặt `self.events` trong app (là hàng đợi nội bộ của `RyuApp` → `'deque' object has no attribute 'put'`, Ryu tê liệt). Thuộc tính nội bộ: `CONF, events, _events_sem, event_handlers, is_active, main_thread, name, observers, threads`.
- Chạy: `ryu-manager --ofp-tcp-listen-port 6653 campus_switch_13.py campus_noc_monitor.py ryu.app.ofctl_rest` (systemd `campus-ryu.service` → `/root/SDN_CONTROLLER-autostart.sh`; bản trên VM trước 04/10 KHÔNG nạp NOC, đã thay, bản cũ `.v1`). Log `/root/ryu.log`. REST 8080 nghe `0.0.0.0` → tới được từ host 1 qua IP LAN `ens6` của node 9 (`10.215.28.71`, DHCP); trên `ens6` chain iptables `CAMPUS_ENS6` (autostart) chỉ cho host 1 `10.215.28.26`, DHCP, ping.
- **NOC v2** `campus_noc_monitor.py`: Campus SDN Console (tab Tổng quan/Topology/Khôi phục/Lưu lượng…), REST `/campus/*`, ping liên tục ICMP raw socket gửi đều theo chu kỳ. Xem `configs/01-Site100-Campus/README_NOC.md` (kèm bảng kết quả đo).
- **Test cục bộ** (không cần lab): `configs/01-Site100-Campus/test/test_campus_tree.py` (logic cây) và `test_campus_ryu.py` (parser OF1.3 thật, cần thư mục chứa gói `ryu` 4.34 + `netaddr`, `six` trong `PYTHONPATH`; stub chặn ghi đè thuộc tính nội bộ `RyuApp`).
- **Triển khai lên node 9**: `MSYS_NO_PATHCONV=1 python scripts/lab/deploy_node9.py <file>=<đích>` (tắt node 9, guestfish, so md5, bật lại; OVS giữ flow nên dữ liệu không mất). Bộ thử: `scripts/lab/sdn_recovery_test.py` (`--links`, `--modes`, `--node 5`).
- **VLAN động (giai đoạn 2)**: `api_vlan_apply(add|ports|delete)` đổi `access_cfg` (VLAN theo cổng hoàn toàn bằng OpenFlow — `tag=` OVSDB chỉ có tác dụng với NORMAL nên không cần sửa), lưu `/root/ryu-app/state/vlans.json` (nạp lại khi khởi động), xoá flow cookie 0 trên switch bị ảnh hưởng + barrier. VLAN mới 2–254 theo quy ước `10.1.<VLAN>.0/24`; controller sinh IOS cho Core (VLAN, trunk allowed Et0/2+Et1/2, SVI .2/.3 + VRRP .1 (150/100), `ip helper 10.1.90.10`, OSPF). Bộ thử: `scripts/lab/sdn_vlan_test.py`. **IOL crash** khi xoá SVI đang là VRRP Master gửi dồn — xoá theo thứ tự `no vrrp`→`shutdown`→OSPF→trunk→`no interface`→`no vlan`, gõ từng lệnh.
- **Chính sách + pipeline 2 bảng (giai đoạn 3)**: bảng 0 = kiểm soát (probe 65000, quản trị 60000, `0xba5f` Access 45000, chặn cây **40000** — phải < 45000 nếu không cắt quản trị Access qua uplink bị chặn, chính sách 20001–20999, mặc định goto 1), bảng 1 = chuyển tiếp (L2 học, table-miss → controller). Luật chỉ cài trên 4 Access (khớp IP, `vlan:N`=10.1.N.0/24), deny=drop, allow=goto 1, cookie `0x5d100000|id` → FlowStats 5 s cho bộ đếm. Lưu `state/policies.json`, cài lại khi Access kết nối. **Xoá theo cookie phải đặt `table_id=OFPTT_ALL`** (Ryu mặc định bảng 0). Bộ thử `scripts/lab/sdn_policy_test.py`.
- **Đo tải (giai đoạn 4)**: NOC poll PortStats + TableStats 5 s, đếm packet-in theo dpid (`api_counters`), CPU/RAM từ `/proc` (không psutil); Core IOL đo qua cổng OVS đối diện (`CORE_UPLINKS`) và CPU qua **SNMP v2c tự viết (BER thuần Python)** từ `/root/ryu-app/state/snmp.json` (0600) `{community, targets}`; Core-SW1/2 đã bật `snmp-server community … RO 98` + ACL 98 permit 10.1.99.10 (04/10, community trong file credentials). NOC dò GETNEXT `cpmCPUTotal5secRev`→`cpmCPUTotal5sec`→`busyPer`/`avgBusy1`. Core-SW1 OK; **Core-SW2 timeout** do Vlan99 của nó cô lập (chỉ Et1/2 → sw5 ens10, OVS bỏ 99) — đổi đích sang 10.1.90.3 cũng vô ích vì gói trả về đi Vlan99. Bộ thử `scripts/lab/sdn_load_test.py`.
- **Còn mở**: lúc Dist-SW1 boot lại (~35 s sau start) toàn bộ probe của Dist-SW2 hết hạn ~3 s (gián đoạn 1,6 s) — nghi gói lạ khi OVS khởi động, chưa điều tra. ONOS vẫn nối song song cổng 6654 (chỉ LLDP/BDDP).
- **OVS mỗi node**: `br0` (`protocols=OpenFlow13`, `other_config:datapath-id`, `set-controller tcp:10.1.99.10:6653`, `fail_mode=secure`, `stp_enable=false`, cổng có `tag=`/`trunks=`), `br-mgmt` + IP mgmt, cặp patch `patch-mgmt`↔`mgmt-peer` (access tag 99). **Không xoá `tag=`/`trunks=`** khỏi script — app dựa vào đó.
- **Persistence (đã triển khai trong repo)**: `Campus-OVS-restore.sh` + `systemd/campus-ovs-restore.service` (oneshot, idempotent) + `systemd/ovs-nodes/<Node>.env` (mỗi node một env: `CAMPUS_DPID`, `CAMPUS_MGMT_CIDR`, `CAMPUS_PHYSICAL_PORTS`, `CAMPUS_TRUNK99_PORTS`, `CAMPUS_BOOTSTRAP99_PORTS`…); controller: `SDN_CONTROLLER-autostart.sh` + `campus-ryu.service`; `Campus-Cloud-DHCP.sh` + `campus-cloud-dhcp.service` (DHCP Cloud-NAT tách khỏi vòng đời Ryu). Đừng đưa script khởi tạo có bước reset OVSDB vào `rc.local`/cron `@reboot`.
- Template `linux-ubuntu-ovs-16p` đã cài sẵn Ryu + app; disk node là qcow2 overlay của template.

## Trạng thái nào còn sau stop/start

| Thành phần | Sau stop/start | Ghi chú |
|---|---|---|
| Script, Ryu, app trên đĩa | còn | mất nếu wipe/đổi image |
| Bridge/port/controller/DPID trong OVSDB | thường còn | vẫn phải kiểm tra — có node từng mất bridge |
| IP gán bằng `ip addr add` | **mất** | phải có `campus-ovs-restore` |
| Flow `add-flow` | **mất** | flow bootstrap phải cài lại |
| Flow reactive + bảng MAC của Ryu | mất | tự học lại sau reconnect |
| Process `ryu-manager` | mất | systemd phải khởi động lại |

Hoàn tất khi: IP mgmt có lại, ping được `10.1.99.10`, `is_connected: true`, REST đủ 6 DPID. Không kết luận "OVS còn cấu hình" chỉ vì bridge xuất hiện.

## VLAN 99: vòng lặp và "cây" quản trị

Topology có vòng thật: Access dual-home 2 Dist, inter-dist ens8, 4 link Dist↔Core, Core1/Core2 cùng nối Farm. OVS không chạy STP.

- **Sự cố 09/2026**: VLAN 99 flood toàn mesh → broadcast storm (≈130–250k pps trên các uplink) → OVS flap/không connect controller. Có hai nguồn: (a) IOL: Core-SW1/2 từng có `no spanning-tree vlan 99` (trạng thái live, không có trong repo); (b) **flow bootstrap `priority=50000,dl_vlan=99,actions=NORMAL`** của `Campus-OVS-restore.sh` — vì 6 OVS boot trước khi Ryu kịp cài TREE-BLOCK nên NORMAL tái tạo vòng.
- **Cây mgmt đã chốt**: `Controller → Farm(E1/0→E0/0) → Core-SW1(Et1/1) → Core-SW1(Et1/2) → sw8.ens10 → sw8.ens8 ↔ sw5.ens8 → sw5.ens4..7 → Access`. Nhánh **không** mang VLAN 99: Core-SW1 Et0/2 (→sw5.ens9), Farm E0/3 (→Core-SW2), Core-SW2 Et0/2 và Et1/2. STP vlan 99 bật lại trên Core: Core-SW1 priority 8192, Core-SW2 12288.
- **Đã làm live (19/09)** trên Core-SW1/2/Farm: prune VLAN 99 các nhánh trên + bật STP vlan 99 + `write memory` — chưa đồng bộ về `configs/`.
- **Đã triển khai 20/09:** script restore đang chạy trên đĩa 6 OVS là bản trong `configs/01-Site100-Campus/ovs-deployed/` (Access ≠ Dist, xem README ở đó), KHÔNG phải `../Campus-OVS-restore.sh` tổng quát. Core/Farm live đã đồng bộ về `configs/`.
- Lịch sử: cách cũ (Codex) là giữ NORMAL và prune bằng `trunks=…` trên vài cổng Dist. Cách mới thay thế nó; nếu gặp tài liệu cũ nhắc "hai flow NORMAL bootstrap", coi là lỗi thời.
- Pruning/bootstrap chỉ giải quyết control plane. Chống loop dữ liệu là việc của app Ryu (`L2_TREE_BLOCK`, flood theo VLAN) — kiểm tra riêng bằng traffic.

## Chẩn đoán DHCP theo lớp

Áp dụng khi VPC báo "Can't find dhcp server". **Dừng ở tầng đầu tiên sai**, không sửa vơ vẩn.

- **A — VPC có phát Discover không?** Tap VPC (`vunl6_14_0`): `tcpdump -e -n 'udp port 68'` phải thấy `0.0.0.0.68 > 255.255.255.255.67` (MAC VPC dạng `00:50:79:66:68:xx`) lặp ~3 s.
- **B/C — Discover tới Core SVI + relay → DHCP-Server?** Theo dấu MAC qua VPC(14_0) → sw68(68_1) → sw5(5_1) → Core(5_6) → Farm(24_17) → DHCP-Server(72_0). Relay đúng thì thấy `10.1.10.2.67 > 10.1.90.10.67` (giaddr 10.1.10.2/.3). Không tới Core ⇒ **datapath SDN chặn** (≈90% ca lịch sử). Xem `/root/ryu.log`, `/stats/flow/<dpid>`, `/stats/switches`.
- **D — OFFER/ACK về VPC?** Relay gửi `10.1.10.2.67 > 10.1.10.100.68` tagged VLAN 10 ngược đường. Lỗi hay ở sw5/sw68 với frame **unicast**.
- Ngoài datapath: nếu Discover tới `vunl6_72_0` mà DHCP-Server không trả OFFER → xem service/scope/giaddr trên node 72 (đã từng là blocker 05/09, sau đó DHCP end-to-end chạy được 15/09).

**3 root cause đã sửa (15/09/2026) — nếu tái diễn kiểm tra theo thứ tự:**
1. **vlan resolve = 0**: DEAD handler `pop` `access_ports` khi switch flap → packet-in resolve vlan 0 → flood rỗng. Sửa: DEAD handler **giữ cấu hình tĩnh** + fallback `_static_access_vlan()` đọc `PORT_CFG`.
2. **OVS lab build không đưa VLAN vào match packet-in**: tag 802.1Q nằm **trong `msg.data`** (`eth.ethertype==0x8100`), match chỉ có `in_port`. Controller tự parse VID; egress theo từng cổng: trunk `PushVlan(0x8100)`+`SetField vlan_vid=OFPVID_PRESENT|vlan` nếu chưa tag, access `PopVlan` nếu đã tag. Import `from ryu.lib.packet import vlan as vlan_pkt` (biến `vlan` int che module → lỗi `'int' object has no attribute 'vlan'`).
3. **`KeyError: unknown OXM field: dl_vlan`** khi cài flow unicast: OF1.3 dùng `vlan_vid = OFPVID_PRESENT | vlan`, không dùng `dl_vlan` (tên OF1.0). Lỗi làm crash handler → DHCP chỉ có D,O thiếu R,A. Dấu hiệu: `ryu.log` có `Traceback … KeyError`.

Đoạn **table-miss**: khi OVS chuyển standalone → `secure` lúc connect, flow NORMAL/VLAN99 của restore script bị xoá → chỉ còn table-miss. App phải tự cài `priority=0 → OUTPUT:NORMAL` mỗi lần connect (đã vá 05/09).

## Khôi phục OVS

Khởi động: Farm/Core → controller → Dist → Access. Trước tiên trên Farm/Core: `show ip interface brief | include Vlan99`, `show interfaces trunk`, `show spanning-tree vlan 99` — sửa hạ tầng Cisco trước, đừng chạy lại script OVS để che lỗi upstream.

Trên controller: `systemctl enable --now campus-cloud-dhcp campus-ryu`; `ip -4 -o addr show dev ens3` (có `10.1.99.10/24`); `ss -ltnp | grep -E '6653|8080'`; `curl -s http://127.0.0.1:8080/stats/switches`; `tail -n 50 /root/ryu.log`.

Trên mỗi OVS, quyết định:
```bash
ovs-vsctl br-exists br0; ovs-vsctl br-exists br-mgmt
ovs-vsctl get bridge br0 other_config:datapath-id
ovs-vsctl get-controller br0
```
- Bridge, DPID, controller đúng → kích hoạt lại `campus-ovs-restore` (`systemctl restart campus-ovs-restore`) — đừng chạy script reset mù quáng.
- **Bế tắc FAILOVER/RECOVERY (gặp lại 03/10/2026 khi cold-start 8 → 5 → Access):** `ryu.log` lặp `FAILOVER`/`RECOVERY`/`DEAD: socket sw5 dong` (đếm `grep -caE FAILOVER` = 152), rồi `LIVENESS: sw5 im lang … sw8 khong ket noi`. Các OVS giữ flow Ryu cũ (vd `priority=50000,dl_vlan=99 actions=drop` chỉ chừa một `in_port`) chặn chính `patch-mgmt` → `ovs-vsctl list controller` báo `No route to host`; `fail_mode=secure` giữ flow hỏng nên Ryu không vào sửa được. **Restart Ryu không đủ.** Cách gỡ đã chạy: trên từng Dist bị kẹt (làm **Dist-SW2 gốc cây trước**, rồi Dist-SW1) `ovs-ofctl -O OpenFlow13 del-flows br0 && systemctl restart campus-ovs-restore` (cài lại bootstrap cookie `0xba5e`) → ~1 phút sau 6/6 nối Ryu, `curl :8080/stats/switches` = `{5,8,66,68,69,70}`, log `Switch 5 ve (khong trong failover)`. Access không cần đụng. Kiểm 6 switch nhanh từ Core-SW1: ping `10.1.99.11/.12/.21–.24`.
- Bridge thiếu/hỏng/OVSDB trống → chạy đúng `/root/<Node>.sh`; nếu script báo trùng bridge và đã xác nhận đúng node + được phép: `ovs-vsctl --if-exists del-br br0; … del-br br-mgmt` rồi chạy lại script. **Không wipe node** để sửa bridge.
- Kiểm tra: `ip -4 -o addr show dev br-mgmt`, `ping -c2 10.1.99.10`, `ovs-vsctl show`, `get bridge br0 protocols|other_config:datapath-id|fail_mode|stp_enable`, `ovs-ofctl -O OpenFlow13 dump-flows br0`. Mong đợi `OpenFlow13`, đúng DPID, `secure`, `false`.

## Triển khai qua console (không SSH)

Node 9 và 6 OVS không mở SSH. Pattern đã dùng (xem `console-automation.md`): heredoc base64 qua VNC/serial → `base64 -d | gzip -d > file` → `chmod` → `md5sum` → marker.

- **Node 9 (controller)**: app đích `/root/ryu-app/campus_switch_13.py` → `sudo systemctl restart campus-ryu` → kiểm tra md5 + `ryu.log`. Sau khi sửa app luôn `ip dhcp` lại VPC14/VPC19 và bắt đủ đường đi/về.
- **6 OVS (datapath)**: đích là **script `.sh`** (`/root/ovs-config/…` hoặc `/root/<Node>.sh`) rồi `bash` script (tự đặt DPID + controller). **KHÔNG** `restart campus-ryu` trên OVS — service đó chỉ có ở node 9. Đừng dùng một md5 chung cho cả 6 node (ghi chú cũ từng nhầm): mỗi `.sh`/`.env` có md5 riêng — tính lại từ file hiện tại.
- Bundle dựng sẵn trong `%TEMP%\opencode\ovs6_bundle*` (nếu còn) đã **lỗi thời** so với working tree — dựng lại từ file hiện tại.
- Mọi sửa app chỉ qua script deploy + lưu về repo; bản repo phải sạch (xoá các dòng log `DBG`).

## Cạm bẫy Ryu/OVS

- REST `ofctl_rest`: `POST … {"type":"OUTPUT","port":"NORMAL"}` sinh flow `actions: []` = **DROP** (tê liệt forwarding); `flowentry/clear` không xoá được → `flowentry/delete` match chính xác + restart Ryu.
- Trên host EVE có `ovs-testcontroller` chiếm 6653 và `tomcat8` chiếm 8080 — nếu node 9 không chạy, đó không phải Ryu.
- `fail_mode=secure` + không có controller ⇒ OVS drop hết ⇒ DHCP broadcast không đi. Nếu switch không connect: xác nhận node 9 chạy **trong đúng lab instance** (xem `eve-ng-ops.md`) trước khi nghi app.
- STP của OVS phải tắt; STP thật nằm ở Cisco.
- Sudo trên OVS/controller: xem file credentials cục bộ. Ngày 18/09 node 5 từ chối mật khẩu đã dùng trên node khác — thử đúng giá trị ghi cho OVS trước, sai thì dừng, đừng thử mò.

## STORM khi một OVS boot/restart: in-band control (nguyên nhân gốc, 20/09/2026)

- **Triệu chứng:** một OVS vừa boot (chưa kết nối controller) → mọi tap Dist/Access lên 50.000–200.000 gói/s; toàn bộ khung là **ARP broadcast của controller** (`00:50:06:00:09:00 → ff:ff:ff:ff:ff:ff`, VLAN 99), xuất hiện cả ở cổng bị cấm VLAN 99; Ryu thấy `[]`; OVS log `no response to inactivity probe`. Có thể kéo dài vô hạn. Dấu hiệu chẩn đoán: `ovs-vswitchd.log` có `in_band|WARN|br0: cannot find route for controller`.
- **Nguyên nhân:** in-band control của OVS cài flow ẨN (không hiện trong `dump-flows`) với action `NORMAL` cho ARP khi chưa kết nối; flood ra mọi cổng, bỏ qua flow chống vòng.
- **Cách sửa (đã nạp lên 6 node):** `ovs-vsctl set Bridge br0 other_config:disable-in-band=true` đặt TRƯỚC `set-controller` trong `/root/Campus-OVS-restore.sh`. Controller đi qua `br-mgmt` (không qua cổng local của `br0`) nên không cần in-band.
- **Đo storm nhanh:** đọc `/sys/class/net/vunl6_<node>_<n>/statistics/{rx,tx}_packets` mỗi 3 s trên host EVE; hoặc `tcpdump -i <tap> -Q in -q -c 300`. Thống kê nguồn/đích/VLAN của 300 gói đầu là đủ để biết loại khung.
- **Không được đọc nhật ký OVS từ đĩa của node ĐANG CHẠY** (cho bản cũ); dừng node rồi đọc mới chính xác.
- **Thiết kế cây quản trị hiện tại:** Access = **nút lá** của VLAN 99 (flow cố định chỉ đi `patch-mgmt` ↔ uplink, không nối cầu 2 uplink) → đồ thị VLAN 99 không có vòng → failover mở Dist-SW2 không cần guard. Không được xóa flow cookie `0xba5f` trên Access (`_flush_output_port` chỉ xóa cookie 0).
- **Khi vá script trên đĩa:** `tag=99` của cổng patch CHỈ có tác dụng với NORMAL — khung từ `br-mgmt` vào OpenFlow không có tag. Access (IP trên `br-mgmt`) cần `mod_vlan_vid:99` / `strip_vlan`; Dist (IP trên `br-mgmt.99`) thì khung đã có tag → **không** dùng strip_vlan (đã làm sw8 mất kết nối 10 phút khi thử).
- **Quy trình vá 1 node offline (không cần đăng nhập):** `unl_wrapper -a stop -D <id>` → chờ tiến trình qemu (`-name <tên>`) biến mất → `guestfish -a virtioa.qcow2 -i upload <file> /root/Campus-OVS-restore.sh; chmod 0755` → `unl_wrapper -a start`. Chờ 6/6 (~2,5 phút) rồi mới sang node sau; vá Dist-SW2 trước Dist-SW1; khi dừng sw8 hoặc sw5 đường quản trị đứt tạm thời (Ryu không failover nếu sw8 không kết nối).
