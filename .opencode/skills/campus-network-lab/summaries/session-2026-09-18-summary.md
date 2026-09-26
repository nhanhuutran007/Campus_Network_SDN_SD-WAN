# Session Summary 2026-09-18 — Node 5 (Dist-SW1) KHÔNG kết nối được SDN controller sau boot lại: datapath mgmt VLAN 99 chết bên trong OVS

## Objective
- Debug vì sao node 5 (Dist-SW1, OVS dpid 5) sau khi start lại/host EVE bật lại **không connect được SDN controller** (Ryu 10.1.99.10:6653) và **không ping được gateway/controller từ br-mgmt 10.1.99.11** → trước mắt: xác định tầng lỗi (OVS bridge bên trong node 5 vs đường VLAN99).

## KẾT QUẢ CHÍNH (bằng chứng đã gather)
1. **Node 5 service OK nhưng datapath mgmt CHẾT.** OCR console node 5 (`node5_state.png`, `node5_diag1.png`): `systemctl is-active campus-ovs-restore` = **active**, `openvswitch-switch` = active, `br-mgmt` có `inet 10.1.99.11/24` (state UNKNOWN).
2. **Ping từ node 5 THẤT BẠI 100%**: `ping 10.1.99.10` (controller) và `ping 10.1.99.1` (gateway) đều trả `From 10.1.99.11 Destination Host unreachable` → **ARP không resolve**.
3. **Capture song song 3 tap** (`vunl6_5_6`→Core-SW1, `vunl6_5_7`→Core-SW2, `vunl6_5_1`→Access-SW1) trong lúc ping: KHÔNG có frame nào src `10.1.99.11` egress; ngược lại thấy rõ **ARP SVI core `who-has 10.1.99.1` + reply `aa:bb:cc:80:36:00` + DNS controller 10.1.99.10→8.8.8.8** tràn trên 2 uplink (core flood, KHÔNG phải node 5 forward), **DHCP dhclient chính node5 MAC `00:50:06:00:05:01`**, ARP `who-has 10.1.99.12` (node 8 đang stopped). → **không có dấu vết .11 egress = node 5 không đưa frame vlan99 của chính nó ra wire**.
4. **Phía controller/core OK**: capture ens3/node9 + taps cho thấy traffic controller đi tới được gateway; `/stats/switches` có lúc `[]` (chưa switch nào connect). Lỗi nằm **TRONG node 5** (br0/patch-mgmt/enslave/flows).
5. **CONSTRAINT VNC (quan trọng)**: vncdotool/vncrun.py **không gõ được ký tự shell đặc biệt `|` `>` `&`** → lệnh `echo ... | sudo -S ...` và redirect `> /tmp/...` bị hỏng (OCR thấy `unpr022026 \ sudo -S ovs-vsctl show bro`, `fold: /tmp/ovs_show.txt: No such file`). Đã viết **`vncovs.py`** (pattern sudo tương tác: gõ `sudo -S <cmd>`, Enter, sleep 3s, gõ pass, Enter, captureScreen) — KHÔNG dùng ký tự đặc biệt.
6. **Sudo password node 5 SAI**: `sudo -S ovs-vsctl show br0` + `vnpro@2026` → `[sudo] password for eve: Sorry, try again`. Chưa biết pass đúng (chưa verify được — từng dùng `vnpro@2026` thành công trên node 8 ở phiên trước nhưng node 5 sai).
7. **EVE host DOWN CUỐI PHIÊN**: sau bước chuẩn bị guestfish đọc disk node 5, mất kết nối hoàn toàn — SSH timeout + ping fail tới `10.215.28.26` và cả `10.215.28.1` (segment gateway), trong khi WLAN local `192.168.2.1` OK. Không đọc được disk.

## Important Details (cập nhật)
- **EVE host 1**: `10.215.28.26` SSH `root`/`#PKT@2026#`. **Lab ACTIVE = `/opt/unetlab/tmp/6/ecf7c5b8-8c91-4616-953e-10b367b388e6/`** (chứ ko phải 7468342c). Runner node 5 pid 27366 cwd = `.../ecf7c5b8.../5`.
- **Node 5 console = VNC port `33541`** (10.215.28.26). Disk: `ecf7c5b8.../5/virtioa.qcow2` (guestfish `--ro` available: `/usr/bin/guestfish`).
- **Ryu (node 9)**: console serial `33713` (per session 17/09) hoặc VNC; REST `http://127.0.0.1:8080` (only from node 9), log `/root/ryu.log`, app `/root/ryu-app/campus_switch_13.py`. Khi switch connect: log phải có `Switch 5 connect` + `/stats/switches` có 5.
- **Tap map (đã verify session 17/09)**: node5 ens9 = vunl6_5_6 (→Core-SW1), ens10 = vunl6_5_7 (→Core-SW2), ens4 = vunl6_5_1 (→Access-SW1). `MAC 00:50:06:00:NN:0X` trên tap = dhclient chính Ubuntu OVS VM (đừng nhầm VPC).
- **OVS design**: `br0` `set-controller tcp:10.1.99.10:6653`, OpenFlow13, dpid `0…<node-id hex>` (=5), `fail_mode=secure`, `stp_enable=false`; `br-mgmt` (VLAN 99) + `patch-mgmt` (access tag=99) nối br0↔br-mgmt; bootstrap flow `priority=50000,dl_vlan=99,actions=NORMAL` từ `Campus-OVS-restore.sh` (đọc `/etc/default/campus-ovs`; Dist-SW1.env có CAMPUS_DPID/MGMT_CIDR/PHYSICAL_PORTS/TRUNK99_PORTS/BOOTSTRAP99_PORTS).
- Host diag: route local tới 10.215.28.x đi qua default 192.168.2.1 (không có route static 10.215.28/24) — khi host down phải chờ host up lại.

## WORK STATE
### Completed
- Xác nhận controller sống + ARP tới gateway OK + tap map 5_6/5_7/5_1.
- OCR: ping .10/.1 = Destination Host unreachable (100%).
- OCR: campus-ovs-restore active.
- OCR: sudo vnpro@2026 = wrong password trên node 5.
- Capture chứng minh không có `.11` egress trên uplinks.
- Viết vncovs.py (interactive sudo) — CHƯA chạy thành công do EVE host down giữa phiên.

### Active (tối nay khi EVE host lên lại)
1. **Check host 1**: ping/ssh `10.215.28.26` OK; nếu host reboot thì kiểm tra lab active instance + add lại route `10.9.1.0/24 via 10.215.28.48 dev pnet0` nếu cần (SD-WAN).
2. **Đọc disk node 5** qua guestfish `--ro`: `/etc/default/campus-ovs` → verify CAMPUS_DPID=5, CAMPUS_MGMT_CIDR=10.1.99.11/24, port lists (PHYSICAL/TRUNK99/BOOTSTRAP99) khớp `configs/01-Site100-Campus/Dist-SW1.sh` + `.env`.
3. **Dump OVS bên trong node 5** (chỉ còn đường VNC + sudo): run `vncovs.py` với `ovs-vsctl show br0` và `ovs-ofctl -O OpenFlow13 dump-flows br0` → xác minh `patch-mgmt` còn không, ens9/ens10 có enslave, flow `priority=50000,dl_vlan=99,NORMAL` còn không, `fail_mode`.
4. **Nếu thiếu flow/port**: áp lại restore (kích hoạt `campus-ovs-restore` hoặc chạy lại `Campus-OVS-restore.sh` theo env). Nếu bridge đúng mà vẫn không egress → thử bật lại ens4-10 / xem dhclient chiếm.
5. **Verify connect**: `ryu.log` thấy `Switch 5 connect` + `/stats/switches` = [5,...]; node5 ping 10.1.99.10 OK.
6. Đồng bộ SKILL/README; KHÔNG commit tự động.

### Blocked
- **EVE host unreachable** (soft-block; resume tối nay).
- Switch OVS **VNC-only, không ssh/serial** → mọi đọc/ghi OVS phải qua VNC console (sudo) + host taps + guestfish disk.
- **vncdotool không gõ được `|` `>` `&`** → chỉ dùng lệnh toàn ký tự thường; redirect/pipe phải tránh (pattern vncovs.py interactive sudo).

## Next Move
Theo mục Active. EVE host tối nay cần được bật lại (check nguồn/mạng); sau đó bước 1-3 trong 30 phút, bước 4-5 trong giờ tiếp.

## Relevant Files
- `configs/01-Site100-Campus/Campus-OVS-restore.sh` (logic restore: br0/br-mgmt/patch-mgmt/flow 50000).
- `configs/01-Site100-Campus/systemd/ovs-nodes/Dist-SW1.env` (source of truth env node 5).
- `configs/01-Site100-Campus/Dist-SW1.sh` (truyền tay gốc).
- `configs/01-Site100-Campus/campus_switch_13.py` (app Ryu; repo = bản sạch, deployed node9 = bản debug chưa sync).
- Temp scripts: `vncovs.py`, `vncrun.py`, `ocr.ps1`, `host_cap5e.py`, `host_readcap.py`; screenshots `node5_*.png`.