# Script restore ĐANG CHẠY trên 6 OVS (20/09/2026)

Bản đã nạp thẳng lên đĩa các node (`/root/Campus-OVS-restore.sh`), khác `../Campus-OVS-restore.sh` (bản tổng quát chưa dùng).

## Điểm then chốt (nguyên nhân storm khi reboot)

1. **Tắt in-band control**: `ovs-vsctl set Bridge br0 other_config:disable-in-band=true`.
   OVS in-band tự cài flow ẨN (không hiện trong `dump-flows`) với action `NORMAL` cho ARP khi chưa kết nối
   được controller (dấu hiệu: log `in_band|WARN|br0: cannot find route for controller`). Flood ARP ra mọi
   cổng, bỏ qua flow chống vòng → broadcast storm (controller ARP broadcast tuần hoàn ~200.000 gói/s) mỗi khi
   một OVS đang boot. Controller đi qua `br-mgmt`, không qua cổng local `br0`, nên in-band không cần.
2. `tag=99` của cổng patch chỉ có tác dụng với action NORMAL: khung từ `br-mgmt` vào OpenFlow không có tag.

## Hai biến thể

- `Campus-OVS-restore.access.sh` — Access-SW1–4 (68, 66, 70, 69). IP trên `br-mgmt` nên flow bootstrap phải gán/bóc tag:
  `patch-mgmt` → `mod_vlan_vid:99` → cả hai uplink; uplink → `strip_vlan` → `patch-mgmt`. Flow **cố định**
  (cookie `0xba5f`, priority 45000), Ryu không xóa; Access không nối cầu VLAN 99 giữa hai uplink.
- `Campus-OVS-restore.dist.sh` — Dist-SW1/SW2 (5, 8). IP trên `br-mgmt.99` (subinterface VLAN) nên khung từ patch
  đã có tag 99, không cần gán/bóc. Bootstrap theo cây `CAMPUS_BOOTSTRAP99_PORTS`; Ryu xóa sau handshake.

## Cập nhật 21/09/2026: thêm ONOS làm controller thứ hai (đã nạp lên cả 6 OVS)

- Dòng controller trong cả hai biến thể giờ là
  `ovs-vsctl --timeout=10 set-controller br0 tcp:10.1.99.10:6653 tcp:10.1.99.10:6654`
  (`6653` = Ryu, chuyển tiếp dữ liệu; `6654` = ONOS, GUI/giám sát topology). Không đổi gì khác.
- md5 mới đang chạy: Access (68, 66, 70, 69) `39055868…`, Dist (5, 8) `9eb0685d…`.
  Bản trước khi sửa (Access `8eeb6adb…`, Dist `a84768d6…`) còn ở `/root/Campus-OVS-restore.sh.bak-onos` trên từng node — khôi phục: `sudo cp` bản `.bak-onos` về `/root/Campus-OVS-restore.sh`.
- Đã kiểm chứng bền vững: reboot Access-SW2 → Ryu 6/6, ONOS thấy lại device, VPC20/21 DHCP + ping OK.
- ONOS (node 9, cổng OpenFlow 6654) cần `allowExtraneousRules=true` và `HostLocationProvider requestInterceptsEnabled=false`, nếu không nó xóa flow của Ryu / chặn ARP. Không bật app `fwd` của ONOS.
