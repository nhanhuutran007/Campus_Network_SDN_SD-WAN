# Triển khai và phục hồi Ryu–OVS Site 100

## Mục lục

- Phạm vi và nguồn cấu hình
- Mapping đã kiểm chứng
- Trạng thái nào còn sau stop/start
- Đường VLAN 99 không vòng lặp
- Quy trình khôi phục sau stop/start
- Khôi phục đầy đủ khi bridge bị mất hoặc hỏng
- Kiểm tra kết quả
- Chẩn đoán nhanh

## Phạm vi và nguồn cấu hình

Tài liệu này áp dụng cho SDN_CONTROLLER node 9 và sáu OVS của Site 100 trong lab `Campus Network SDN SD-WAN.unl`. Control plane OpenFlow 1.3 chạy trên VLAN 99 MANAGEMENT qua hạ tầng uplink campus; không khôi phục mạng hoặc link control cũ `10.1.100.0/24`.

Luôn đọc lại các file nguồn trước khi deploy vì chúng có thể thay đổi sau khi tài liệu này được viết:

- `configs/01-Site100-Campus/SDN_CONTROLLER.sh`
- `configs/01-Site100-Campus/Dist-SW1.sh`, `Dist-SW2.sh`
- `configs/01-Site100-Campus/Access-SW1.sh` đến `Access-SW4.sh`
- `configs/01-Site100-Campus/campus_switch_13.py`
- `configs/01-Site100-Campus/SDN_CONTROLLER-autostart.sh`
- `configs/01-Site100-Campus/Campus-Cloud-DHCP.sh`
- `configs/01-Site100-Campus/Campus-OVS-restore.sh`
- `configs/01-Site100-Campus/systemd/`
- cấu hình Core-SW1/2 và SwitchServerFarm trong cùng thư mục

Không lưu credential trong skill hoặc lệnh. Linux/OVS là node cấu hình tay (`config="0"`); không giả định EVE-NG tự nạp các script `.sh`.

## Mapping đã kiểm chứng

| Node | Thiết bị | IP management | Datapath ID | Script trong guest |
|---:|---|---|---|---|
| 9 | SDN_CONTROLLER | `10.1.99.10/24` trên `ens3` | — | `/root/SDN_CONTROLLER-autostart.sh` |
| 5 | Dist-SW1 | `10.1.99.11/24` | `0000000000000005` | restore + `Dist-SW1.env` |
| 8 | Dist-SW2 | `10.1.99.12/24` | `0000000000000008` | restore + `Dist-SW2.env` |
| 68 | Access-SW1 | `10.1.99.21/24` | `0000000000000044` | restore + `Access-SW1.env` |
| 66 | Access-SW2 | `10.1.99.22/24` | `0000000000000042` | restore + `Access-SW2.env` |
| 70 | Access-SW3 | `10.1.99.23/24` | `0000000000000046` | restore + `Access-SW3.env` |
| 69 | Access-SW4 | `10.1.99.24/24` | `0000000000000045` | restore + `Access-SW4.env` |

Controller phải dùng:

```bash
ryu-manager --ofp-tcp-listen-port 6653 \
  /root/ryu-app/campus_switch_13.py ryu.app.ofctl_rest
```

REST lắng nghe TCP 8080. Thứ tự phần tử của `/stats/switches` phụ thuộc thứ tự TCP handshake; so sánh theo tập DPID, không bắt buộc thứ tự JSON.

## Trạng thái nào còn sau stop/start

EVE-NG stop/start thông thường giữ đĩa overlay của QEMU nhưng làm mất trạng thái đang chạy trong RAM. Wipe là trường hợp khác và có thể đưa node về base image.

| Thành phần | Sau stop/start | Ghi chú |
|---|---|---|
| File script, Ryu đã cài và app trên đĩa | Thường còn | Chỉ mất nếu wipe/đổi image hoặc đĩa không được giữ |
| Bridge, port, controller target, DPID trong OVSDB | Thường còn | `ovs-vsctl` ghi vào OVSDB; vẫn phải kiểm tra vì lab từng thấy bridge bị thiếu trên một số node |
| IP gán bằng `ip addr add/replace` | Mất | Phải gán lại hoặc có boot service/netplan |
| Flow cài bằng `ovs-ofctl add-flow` | Mất | Datapath flow là runtime; flow bootstrap VLAN 99 phải cài lại |
| Flow reactive và bảng MAC của Ryu | Mất | Tự học lại sau khi switch reconnect và có traffic |
| Process `ryu-manager` | Mất | Trừ khi boot service khởi động lại thành công |
| Cấu hình Cisco đã `write memory` | Thường còn | Kiểm tra lại VLAN 99/SVI/trunk sau boot |
| DHCP trên controller `ens6` | Xin lại khi có Cloud-NAT | `campus-cloud-dhcp.service` quản lý độc lập; restart Ryu không tạo lease trùng |

Vì vậy không kết luận “OVS còn cấu hình” chỉ từ việc bridge xuất hiện. Điều kiện hoàn tất là management IP có lại, ping được controller, `is_connected: true` và REST đủ sáu DPID.

## Đường VLAN 99 không vòng lặp

`fail_mode=secure` cần flow bootstrap để management ARP/TCP đi qua `br0` trước khi Ryu kết nối. Hai flow `NORMAL` cho VLAN 99 chỉ an toàn khi VLAN 99 được giới hạn thành cây không vòng lặp.

Đường đã kiểm chứng:

- SDN_CONTROLLER `ens3` ↔ SwitchServerFarm `Et1/0` access VLAN 99.
- SwitchServerFarm `Et0/0` ↔ Core-SW1 `Gi1/1`, và `Et0/3` ↔ Core-SW2 `Gi1/1`: trunk VLAN `90,99`.
- Dist-SW1 dùng nhánh VLAN 99 chính qua `ens9` ↔ Core-SW1 `Gi0/2`.
- Dist-SW2 dùng nhánh VLAN 99 chính qua `ens9` ↔ Core-SW2 `Gi0/2`.
- Access-SW1/2 đi VLAN 99 qua Dist-SW1; Access-SW3/4 đi VLAN 99 qua Dist-SW2.

Giữ các VLAN dữ liệu trên mọi trunk nhưng bỏ VLAN 99 khỏi các nhánh management dự phòng sau:

```bash
# Dist-SW1: bỏ VLAN 99 trên nhánh Access-SW3/4, peer Dist và Core-SW2
for p in ens6 ens7 ens8 ens10; do
    ovs-vsctl set port "$p" trunks=10,20,30,40,90
done

# Dist-SW2: bỏ VLAN 99 trên nhánh Access-SW1/2, peer Dist và Core-SW1
for p in ens4 ens5 ens8 ens10; do
    ovs-vsctl set port "$p" trunks=10,20,30,40,90
done
```

Các cổng còn lại giữ `trunks=10,20,30,40,90,99`. Không bật `stp_enable` trên OVS để tránh chặn frame trước OpenFlow pipeline. STP trên Cisco vẫn phải ổn định và các trunk VLAN 99 phải forwarding.

Pruning này chỉ bảo vệ flow bootstrap `NORMAL` của VLAN 99. Không dùng kết quả reconnect control plane để kết luận các VLAN dữ liệu đã chống loop; phải kiểm tra riêng logic flood/topology của app Ryu và traffic data plane.

## Quy trình khôi phục sau stop/start

### 1. Khởi động và kiểm tra hạ tầng VLAN 99

Khởi động theo thứ tự: SwitchServerFarm/Core → SDN_CONTROLLER → Dist-SW1/2 → Access-SW1–4.

Trước khi controller chạy, trên SwitchServerFarm/Core kiểm tra SVI, trunk và STP:

```text
show ip interface brief | include Vlan99
show interfaces trunk
show spanning-tree vlan 99
```

Mong đợi SVI VLAN 99 `up/up`, VLAN 99 nằm trong tập allowed/active/forwarding. Nếu chưa đạt, sửa hạ tầng Cisco trước; không lặp lại script OVS để che lỗi upstream.

### 2. Khởi động controller

Vào root trên node 9 rồi kiểm tra service persistence:

```bash
systemctl enable --now campus-cloud-dhcp.service campus-ryu.service
systemctl is-active campus-cloud-dhcp.service campus-ryu.service
ip -4 -o addr show dev ens3
ss -ltnp | grep -E '6653|8080'
curl -s http://127.0.0.1:8080/stats/switches
```

`ens3` phải có `10.1.99.10/24`; Ryu phải nghe `0.0.0.0:6653` và REST `0.0.0.0:8080`. `campus-cloud-dhcp.service` giữ DHCP `ens6` tách khỏi vòng đời Ryu: khi nối Cloud-NAT controller có Internet, còn khi Cloud vắng thì Ryu vẫn khởi động.

Sau khi controller đã có IP, quay lại một thiết bị Cisco trên VLAN 99 và `ping 10.1.99.10` để xác minh đường đến controller trước khi phục hồi OVS.

### 3. Quyết định khôi phục nhanh hay đầy đủ trên mỗi OVS

Sau khi vào root:

```bash
ovs-vsctl br-exists br0; echo "br0_rc=$?"
ovs-vsctl br-exists br-mgmt; echo "br_mgmt_rc=$?"
ovs-vsctl get bridge br0 other_config:datapath-id
ovs-vsctl get-controller br0
```

- Hai bridge tồn tại, DPID và controller đúng: dùng khôi phục nhanh bên dưới.
- Bridge thiếu, port sai hoặc OVSDB trống: dùng mục “Khôi phục đầy đủ”.
- Không chạy lại script reset OVSDB một cách mù quáng khi bridge đang tốt.

### 4. Khôi phục nhanh trên OVS

Bật NIC vật lý đúng nhóm:

```bash
# Dist-SW1/2
for p in ens4 ens5 ens6 ens7 ens8 ens9 ens10; do ip link set "$p" up; done

# Access-SW1–4
for p in ens4 ens5 ens6 ens7; do ip link set "$p" up; done
```

Trên từng node, thay đúng IP và DPID theo bảng mapping:

```bash
ip link set br0 up
ip link set br-mgmt up
ip addr replace 10.1.99.X/24 dev br-mgmt

ovs-vsctl set bridge br0 protocols=OpenFlow13
ovs-vsctl set bridge br0 other_config:datapath-id=DPID_16_HEX
ovs-vsctl set-controller br0 tcp:10.1.99.10:6653
ovs-vsctl set bridge br0 fail_mode=secure
ovs-vsctl set bridge br0 stp_enable=false
```

Áp lại pruning VLAN 99 trên Dist-SW1/2 như mục “Đường VLAN 99 không vòng lặp”. Sau đó cài hai flow bootstrap trên cả sáu OVS:

```bash
SDN_PATCH_OFPORT="$(ovs-vsctl get Interface patch-mgmt ofport)"
test "$SDN_PATCH_OFPORT" -ge 1

ovs-ofctl -O OpenFlow13 add-flow br0 \
  'priority=50000,dl_vlan=99,actions=NORMAL'
ovs-ofctl -O OpenFlow13 add-flow br0 \
  "priority=50000,in_port=${SDN_PATCH_OFPORT},actions=NORMAL"
```

Trong thứ tự tạo bridge hiện tại, `patch-mgmt` thường là ofport 8 trên Dist và 5 trên Access, nhưng luôn đọc động bằng `ovs-vsctl`; không hard-code khi chưa kiểm tra.

## Khôi phục đầy đủ khi bridge bị mất hoặc hỏng

Nếu `/root/<script>.sh` còn và khớp checksum/source trong repo, chạy đúng script của node:

```bash
bash /root/Dist-SW1.sh
# hoặc Dist-SW2.sh / Access-SW1.sh ... Access-SW4.sh
```

Nếu script báo bridge/port đã tồn tại và cấu hình hiện tại thực sự cần dựng lại, chỉ sau khi xác nhận đúng node và được phép xóa cấu hình OVS:

```bash
ovs-vsctl --if-exists del-br br0
ovs-vsctl --if-exists del-br br-mgmt
bash /root/<script-dung-cua-node>.sh
```

Không wipe node để xử lý lỗi bridge. Sau khi chạy script, luôn áp lại pruning VLAN 99 trên hai Dist và hai flow bootstrap như phần khôi phục nhanh.

Nếu script trong guest bị mất, lấy đúng file từ `configs/01-Site100-Campus/`, paste từng dòng qua console, kiểm tra checksum khi có thể rồi mới chạy. Không tự sửa IP/DPID trong lúc paste.

## Kiểm tra kết quả

Trên mỗi OVS:

```bash
ip -4 -o addr show dev br-mgmt
ping -c 2 -W 1 10.1.99.10
ovs-vsctl show
ovs-vsctl get bridge br0 protocols
ovs-vsctl get bridge br0 other_config:datapath-id
ovs-vsctl get bridge br0 fail_mode
ovs-vsctl get bridge br0 stp_enable
ovs-ofctl -O OpenFlow13 dump-flows br0
```

Mong đợi ping không mất gói, `is_connected: true`, `OpenFlow13`, đúng DPID, `secure`, `false`, và có hai flow bootstrap priority 50000.

Trên controller:

```bash
curl -s http://127.0.0.1:8080/stats/switches
tail -n 50 /root/ryu.log
```

Tập DPID phải là `{5, 8, 66, 68, 69, 70}`. JSON có thể xuất hiện theo thứ tự kết nối, ví dụ `[70, 68, 8, 66, 5, 69]`; đây vẫn là kết quả đầy đủ.

## Chẩn đoán nhanh

| Hiện tượng | Kiểm tra ưu tiên | Hành động |
|---|---|---|
| `br0` hoặc `br-mgmt` không tồn tại | `ovs-vsctl show` | Chạy đúng script node; chỉ xóa bridge trùng/hỏng khi đã được phép |
| `Network is unreachable` trên OVS | IP `br-mgmt`, link, patch pair | Gán lại IP, bật interface, kiểm tra `patch-mgmt`/`mgmt-peer` |
| OVS không ping được `10.1.99.10` | VLAN 99, pruning, flow priority 50000, trunk Core | Sửa L2 reachability trước khi kiểm tra TCP 6653 |
| Ping được controller nhưng `is_connected: false` | `ss` trên controller, target, OpenFlow version | Khởi động Ryu; đặt lại controller và `protocols=OpenFlow13` |
| REST là `[]` | Ryu log và từng OVS | Kiểm tra TCP 6653/DPID; không suy luận chỉ từ ping |
| REST thiếu một DPID | `ovs-vsctl show` trên node tương ứng | Kiểm tra đúng IP, DPID và flow bootstrap node đó |
| Kết nối mất sau restart OVS | `dump-flows br0` | Cài lại hai flow bootstrap; flow runtime không nằm trong OVSDB |

## Persistence đã triển khai

Bộ nguồn chuẩn nằm tại `configs/01-Site100-Campus/`:

- `Campus-OVS-restore.sh` + `systemd/campus-ovs-restore.service` + đúng file `systemd/ovs-nodes/*.env` cho mỗi OVS.
- `SDN_CONTROLLER-autostart.sh` + `systemd/campus-ryu.service` cho Ryu.
- `Campus-Cloud-DHCP.sh` + `systemd/campus-cloud-dhcp.service` cho Cloud-NAT `ens6`.

`campus-ovs-restore.service` là oneshot idempotent, được enable vào cả `multi-user.target` và `openvswitch-switch.service.wants`; khi flow priority 50000 chưa tồn tại script dùng `add-flow`, còn khi đã có thì dùng `--strict mod-flows`. Canary thực tế phải gồm restart `openvswitch-switch.service`, chờ reconnect, rồi kiểm tra lại IP, hai flow, ping và `is_connected: true`.

Không đưa các script khởi tạo cũ có bước reset OVSDB vào `rc.local` hoặc crontab `@reboot`. Sau wipe phải copy và enable lại bộ persistence trên; stop/start QEMU thông thường được systemd tự phục hồi.
