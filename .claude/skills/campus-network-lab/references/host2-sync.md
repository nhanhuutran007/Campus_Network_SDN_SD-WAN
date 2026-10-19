# Đồng bộ host 2 theo host 1 — tiến độ và cách làm tiếp

Snapshot **27/09/2026**, cập nhật **19/10/2026**. Host 2 = EVE boot USB trong VMware trên laptop (IP `10.0.227.112`, tenant 0, 8 vCPU / 8 GB RAM; laptop 16 GB). Host 1 = `10.215.28.26` (tenant 6). Host 2 không tới thẳng host 1 → mọi dữ liệu relay qua PC.

## Đồng bộ đầy đủ 19/10/2026 (mục tiêu: chạy được khi mất host 1 + VPN)

Làm lúc **host 1 tắt toàn bộ lab** (đĩa nhất quán). Kết quả, đều so md5 hai đầu:
- `.unl` (md5 `744a7d6c…`, 72 node/105 net) và thư mục config `labs/…/Campus Network SDN SD-WAN/` giống hệt host 1.
- **37/37 overlay** qcow2 (mọi node trừ 33) khớp md5 toàn file, `qemu-img check` sạch. Chép **delta theo khối 4 MiB** (`bhash.py` băm hai đầu → `delta.py` chỉ gửi khối khác, gzip): 5,8 GB khối đổi, ~25 phút thay vì ~30 GB.
- nvram IOL: nội dung **không phụ thuộc tenant** (chỉ đổi tên `nvram_<id*16+T>`) → chép thẳng; 3/4 đã cập nhật. **`vlan.dat-<id*16+T>`** cũng phải đồng bộ (VLAN của switch VTP server) → 3, 4, 32, 61 đã chép. Bật thử Core-SW1 trên host 2: lên đúng cấu hình. IOL tự ghi lại nvram khi chạy → bật thử xong phải chép lại bản host 1.
- File nhỏ (`startup.vpc`, `startup-config`, `day0-config`, `config.iso`, `minidisk`) giống hệt; node 1 đã chép lại.
- **CA SD-WAN** (`/home` của vManage 33, trích bằng `guestfish --ro` → `tar-out /home`: `admin/ca/root-ca.key/.pem/.srl` + CSR/CRT mọi controller/vEdge) và `/root` host 1 (`sdwan-ca-v2`, `backup-sdwan-20260829`, `n72*`, script) → host 2 `/root/h1-backup-20261019/` (chmod 600). Đã kiểm key khớp cert `SDWAN-Lab-RootCA` (hạn 2036), `openssl verify` vsmart.crt OK. Trích private key bị auto mode chặn, cần người dùng duyệt.
- Bản cũ của host 2 trước khi ghi đè: `/root/h2-before-sync-20261019/` (`.unl`, nvram/vlan.dat, labdir, node 1).
- **Node 64 → id 75 CHỈ trên host 2** (19/10): EVE tính device-id IOL = `(node_id & 0x3f) << 4 | tenant` (`cli.php`), node 64 ở tenant 0 ra 0 ⇒ không chạy. Đã đổi `<node id="64" name="SwitchBrand"` và `<config id="64">` thành 75 (6 bit thấp 11, không trùng IOL nào), đổi thư mục `64`→`75`, `nvram_00000`→`nvram_00176`, `vlan.dat-00000`→`vlan.dat-00176`. Bật thử: `SwitchBrand-S400` đúng cấu hình; nvram đã trả về bản host 1. Console host 2 = 32843. ⇒ `.unl` host 2 **cố ý khác** host 1 đúng 2 chỗ này; khi đồng bộ lại `.unl` phải áp lại (`fix64.py` trong `scripts/host2-sync/`, thay đúng 2 chuỗi trên).
- **Bản giống hệt host 1 để phục hồi 100% lên server mới**: `/root/h1-backup-20261019/lab-h1-exact.unl` (md5 `744a7d6c…`) + `node64-h1-exact/` (thư mục node 64 gốc). Server mới tenant ≠ 0 thì dùng bản này, không dùng `.unl` đã đổi id.
- Bản vá `.lock` (`CAMPUS-PATCH` trong `start()` của `cli.php`) **đã có sẵn** trên host 2; md5 `cli.php` khác host 1 chỉ do khác phiên bản EVE.
- **vManage 33 — ĐÃ CHÉP XONG 19/10 06:18** (chỉ để lưu, KHÔNG chạy trên host 2 vì `ram=32768`): `virtioa` md5 `718b1eb4…`, `virtiob` md5 `645188c2…` khớp host 1, `qemu-img check` sạch; host 2 còn trống 78 GB. Mất ~4 giờ (VPN ~1,8 MB/s, dữ liệu DB khó nén; 2 lần Claude Code dừng lệnh nền vì laptop cạn RAM — lần 2 chỉ chết lớp vỏ, `bigcopy` vẫn chạy). Bẫy Windows: dừng task/monitor **không** giết tiến trình con (bigcopy cũ chạy song song, `vpnwatch` cũ còn sống sau khi monitor hết hạn) ⇒ kiểm `Get-CimInstance Win32_Process` theo CommandLine và kill theo PID; script theo dõi nên tự thoát trước 30 phút (`watch.sh`). Chép bằng `bigcopy.py` (đoạn 1 GiB; trước mỗi đoạn so md5 hai đầu, khớp thì bỏ qua ⇒ chạy lại an toàn kể cả khi mất file tiến độ). **Chạy việc dài trong `C:\Users\nhanh\campus-h2sync\`, không trong scratchpad Temp**: 19/10 ~02:48 scratchpad bị xoá sạch giữa chừng (cùng lúc laptop cạn RAM, Claude Code dừng lệnh nền) ⇒ mất script + file tiến độ.
HANHMPUS-H2SYNC`, KHÔNG TRONG SCRATCHPAD TEMP**: 19/10 ~02:48 SCRATCHPAD BỊ XOÁ SẠCH GIỮA CHỪNG (CÙNG LÚC LAPTOP CẠN RAM, CLAUDE CODE DỪNG LỆNH NỀN) ⇒ MẤT SCRIPT + FILE TIẾN ĐỘ.
- Các file `.bak*` cũ trong thư mục node host 1 không chép.
- Lần sau: chạy lại `bhash.py` hai đầu + `delta.py` (chỉ khi node trên host 1 đã tắt), so nvram/vlan.dat bằng md5 nội dung; nhớ node 64 ↔ 75.

## Mục lục
- Đồng bộ đầy đủ 19/10/2026
- Tổng kết
- Trạng thái từng node
- Việc còn lại (thứ tự đề xuất)
- Cách làm (script, quy trình)
- Bẫy đã gặp

## Tổng kết

| Mức | Node | % (67 node) |
|---|---|---|
| Đã đồng bộ cấu hình/đĩa | 65 | ≈97% |
| Đã bật trên host 2 + so `show run` với host 1 | 22 | ≈33% |
| Đã copy đĩa, `qemu-img check` sạch, **chưa bật thử** | 27 | ≈40% |
| VPC (config nhúng, tự nạp) — chưa bật thử | 16 | ≈24% |
| Không đồng bộ | 2 (33, 64) | ≈3% |

Chưa từng chạy **cả topology** trên host 2 (host 1 dùng ~45 GB RAM) — chỉ chạy được từng nhóm.

## Trạng thái từng node

**A. So live với host 1 và đã khớp (cấu hình text, lưu `write memory`)**
- IOL/vIOS: 3, 4 (Core, diff 0), 7 SwitchDMZ, 24 SwitchServerFarm (diff 0), 32 Switch32, 55–60 (SW), 61 Switch61, 62/63 SwitchBrand, 26 Internet (Gi0/0 để `dhcp` — host 1 dùng IP tĩnh LAN của host 1), 27 MPLS.
- ASAv: 1 + 2 (HA bật đồng thời, Standby Ready, có ACL `INSIDE_OUT`), 37/38/39 Brand-FW (SLA 10 + track 1; chỉ khác thứ tự dòng `inspect`).
- vEdge1-S200 (29): bật trên host 2, login OK, hostname đúng.

**B. Đĩa copy từ host 1 (md5 hai đầu + `qemu-img check` sạch), CHƯA bật thử trên host 2**
- SDN: controller 9, Dist 5/8, Access 66/68/69/70.
- SD-WAN: vEdge 6, 28, 30, 31, 40, 41, 42, 65; vSmart 34; vBond 35.
- Server: Mail 13, Web 22, Syslog 25, DHCP/DNS 72.
- PC: Linux 18/47/52/53, Win 36 (quản trị), 73 (PC-Management).

**C. VPC** 14–17, 19–21, 43–46, 48–51, 54: config nhúng trong `.unl`, EVE nạp mỗi lần start.

**D. Không đồng bộ**
- 33 vManage: `ram=32768`, đĩa ~50 GB (`virtiob` 43 GB) — host 2 không chạy nổi.
- 64 SwitchBrand-S400: IOL device-id = (64×16 + 0) mod 1024 = 0 ⇒ không chạy ở tenant 0.
- 65 vEdge65: đĩa đã copy nhưng người dùng cho bỏ qua kiểm tra.

**Thay đổi trên host 2 khác trạng thái ban đầu**: `.unl` (bản cũ `/root/unl-backup/h2-before-sync-20260927.unl`); base `asav-9-20-2-2` và `linux-ubuntu-ovs-16p` thay bằng bản host 1 (bản cũ `/root/base-backup-20260927/`); thêm image `linux-ubuntu-18.04-server`.

## Việc còn lại (thứ tự đề xuất)

1. **Bật thử theo nhóm vừa 8 GB RAM**, mỗi nhóm xong thì tắt:
   - SDN Site 100: 3, 4, 24, 72 (DHCP), 9 → 5, 8 → 66/68/69/70 → vài VPC; kiểm Ryu `curl localhost:8080/stats/switches` = 6 switch, VPC `ip dhcp`.
   - Một chi nhánh (vd S200): 26, 27, 29, 42, 37, 55, 56, 63, 47 + vSmart 34 + vBond 35 (không có vManage) — kiểm `show control connections`, `show omp peers`, `show bfd sessions`.
   - Server/PC qua VNC trong GUI host 2 (Windows/Ubuntu GNOME không có console text).
2. **Host 1 đã đổi sau snapshot (27/09 tối)**: FW-ASAv-Active thêm `class-map DNS_CONN` + `set connection timeout idle 0:00:10` trong `global_policy` (sửa lỗi IMAP/DNS do giới hạn 100 conn) → áp lên host 2 FW 1+2 (bật cả hai cho HA replicate), rồi `cmp_run.py 1`.
   - Website mới (27/09 tối): `configs/01-Site100-Campus/Web-Server/files/index.html` (md5 `a017430a…`) đã vào đĩa node 22 host 1 bằng `virt-copy-in` (node tắt) → chép tương tự vào `/opt/unetlab/tmp/0/<uuid>/22/virtioa.qcow2:/var/www/campus/` trên host 2 (node tắt), so `virt-cat | md5sum`.
   - `.unl` host 1 đổi 28/09 (md5 `0963bbee…`: 50 chú thích IP/cổng + 16 VPC đổi tên) → upload lên host 2 (backup bản cũ), `validate`.
   - Router Internet (26) 28/09: NAT PAT ra Gi0/0 (DHCP) — dán thêm các dòng NAT từ `configs/06-ServiceProvider/Internet/config.cfg`; Gi0/0 trên host 2 nhận DHCP theo LAN của host 2.
3. Khi host 1 thay đổi: dump lại `show run` (script `h1run.py`) và `cmp_run.py` với host 2; node đĩa thì copy lại (node đang chạy phải tắt tạm trên host 1).
3. Quyết định: có copy vManage 33 (nhiều giờ) hay chấp nhận SD-WAN host 2 không có GUI.

## Cách làm (script trong `scripts/host2-sync/`)

Chạy từ một **thư mục tạm** (script ghi log `log_<id>.txt`, `h1_<id>.txt`, `done.txt` vào thư mục hiện tại) — copy script ra scratchpad rồi chạy. Mật khẩu đọc từ `~/.claude/campus-lab-credentials.md` lúc chạy. Git Bash: `export MSYS_NO_PATHCONV=1 PYTHONIOENCODING=utf-8` (không thì `/opt/...` bị đổi thành đường dẫn Windows).

| Script | Việc |
|---|---|
| `eve.py h1|h2 "<cmd>"` / `put|get` | SSH/SFTP tới host (`EVE_H2=<ip>` nếu IP host 2 đổi) |
| `con.py start|stop|status <id>` | điều khiển node host 2 (`-T 0`) |
| `sync_ios.py <id>…` / `sync_asa.py <id>…` | start → dán `configs/` → `write memory` → so → stop |
| `fix.py <id> ios|asa "l1;;l2"` | start → áp vài dòng → lưu → lưu `show run` vào `log_<id>.txt` → stop |
| `h1run.py <id> ios|asa` | dump running-config host 1 (chỉ đọc) → `h1_<id>.txt` |
| `cmp_run.py <id>` | diff host 1 ↔ host 2 |
| `h1lines.py <id>` | biến running-config host 1 thành dòng dán (bỏ cert chain, mật khẩu băm, pager) |
| `bhash.py <labdir> <out>` (chạy trên host) / `delta.py <id>…` (PC, cần `h1_bh.txt`, `h2_bh.txt`, `bread.py`/`bwrite.py` ở `/tmp` hai host) | chép overlay chỉ các khối 4 MiB khác, so md5 toàn file |
| `relay2.py -l <list>` | copy file host 1 → host 2 (gzip, md5 hai đầu, retry, bỏ qua mục trong `done.txt`); dòng list `src|dst|owner` |
| `hotcopy.py <id>…` | node ĐANG chạy trên host 1: stop → copy → start lại → kiểm console |
| `vlogin.py` / `h1v.py <id> <credtag> "cmd;;cmd"` | đăng nhập Viptela an toàn (dừng sau 1 lần sai) |
| `n9.py <serial-port> "cmd;;cmd"` | shell node 9 qua serial (port động: `ss -tlnp` theo pid qemu `-name SDN_CONTROLLER`) |

Overlay qcow2 host 1: `/opt/unetlab/tmp/6/<lab-uuid>/<id>/virtioa.qcow2` → host 2: `/opt/unetlab/tmp/0/<lab-uuid>/<id>/`, owner `unl0:unl`. Lab-uuid `ecf7c5b8-8c91-4616-953e-10b367b388e6`.

## Bẫy đã gặp

- Base image phải **giống hệt** trước khi copy overlay (so `md5sum` toàn file).
- Copy overlay của node đang chạy = đĩa hỏng → phải tắt node trên host 1 (tắt/bật controller 34/35 không mất whitelist — đã kiểm 27/09; sau khi bật Dist-SW1, Ryu có lúc `[]` rồi tự về `[5, 8]`).
- Relay ~1,5–4 MB/s (gzip -1 giúp ~4×); node 9 (3,6 GB) mất ~20 phút ⇒ controller host 1 tắt lâu.
- vEdge: `login:` hiện trước khi confd sẵn sàng ⇒ chờ ~3 phút, không thử lại liên tục (khoá 15 phút).
- IOS: dán `banner … ^C` nuốt các dòng sau; vIOS mặc định interface `shutdown` nên cần `no shutdown`; `end` ở exec mode bị hiểu là tên host (tra DNS).
- ASA: dán config có `pager lines 24` làm bật lại pager; `route … track 1` phải đứng sau `track 1`.
- Thư mục node qemu trên host 2 có "jail" bind-mount: file trong `/opt/unetlab/addons` hiện thêm dưới `<node>/opt/...` — cùng inode, không tốn đĩa.
- Auto-mode classifier chặn thao tác tắt node đang chạy trên host 1 dù có lời cho phép trong chat — người dùng đã cấp quyền rõ ràng 27/09.
