# Vận hành EVE-NG: config nhúng, đồng bộ, deploy

Giá trị host/IP/đường dẫn dưới đây là **lịch sử** (2026-09) — xác nhận lại trước khi dùng cho lệnh có tác động thật. Không có mật khẩu trong tài liệu này: đọc `C:\Users\nhanh\.claude\campus-lab-credentials.md` (cục bộ, ngoài repo).

## Mục lục
- Cơ chế config nhúng (quan trọng nhất)
- Sửa `.unl` an toàn
- Chiều đồng bộ và deploy
- Node nguy hiểm khi wipe
- Console, port, start/stop
- Node "start im lặng" (.lock)
- Host 2 dự phòng
- Truy cập vManage GUI từ xa
- Bẫy hay gặp khi viết script trên host EVE

## Cơ chế config nhúng (quan trọng nhất)

- EVE **chỉ** nạp startup config từ khối `<configs><config id="N">base64</config></configs>` bên trong `.unl`, và chỉ khi node có `config="1"` + payload không rỗng. File `config.cfg`/`config.txt` trong thư mục node trên server **không** được EVE đọc lúc start — chỉ dùng để paste tay/đồng bộ. (Đã debug từ source: `__lab.php` ép `config="0"` nếu thiếu payload; `cli.php` chỉ dump khi cờ bật + có data.)
- `config="1"` ≠ chắc chắn đã nạp: **IOL chi nhánh (SwitchBrand/SW), Switch32, vEdge** thường không nạp khi start bằng `unl_wrapper` → phải dán tay và `write memory`/`commit`. **Core-SW1/2 IOL** và **ASAv** nạp được. Luôn xác minh hostname/VLAN sau boot rồi mới kết luận.
- GUI EVE **ghi đè `.unl`** khi mở/save lab: reset `config="1"`→0 và mất config nhúng. Không mở/save lab bằng GUI; không dùng chu kỳ Delete lab → Import lại (commit `5222ac6` từng phải sửa hậu quả).
- Linux/OVS, Windows, vtmgmt/vtsmart/vtbond là `config="0"`: `.sh`/GUI/CLI thủ công.

## Sửa `.unl` an toàn

Dùng `scripts/unl_tool.py` (chạy từ repo, không cần EVE):

```powershell
python .claude/skills/campus-network-lab/scripts/unl_tool.py validate      # bắt buộc sau mọi thay đổi .unl
python .claude/skills/campus-network-lab/scripts/unl_tool.py drift         # config nhúng vs configs/
python .claude/skills/campus-network-lab/scripts/unl_tool.py embed 3 configs/01-Site100-Campus/Core-SW1/config.cfg          # dry-run
python .claude/skills/campus-network-lab/scripts/unl_tool.py embed 3 configs/01-Site100-Campus/Core-SW1/config.cfg --write
git diff --stat "Campus Network SDN SD-WAN.unl"                            # phải đổi đúng khối mong muốn
```

Quy tắc:
- Thay khối `<config id>` ở **mức byte**. Đừng parse-rồi-serialize bằng `ElementTree.write` hay mở text-mode (đổi EOL → diff hàng nghìn dòng). File `.unl` chuẩn dùng LF; payload bên trong giữ nguyên EOL của file nguồn (một số config chứa CRLF).
- Bảo toàn node-id, network-id, interface mapping không liên quan. Số link trong bảng 2.2.x của `campus_network_sdn_sdwan.md` phải khớp `.unl` (đối chiếu tay — công cụ chưa tự kiểm).
- Thêm node mới: thêm `<node>` + bật `config="1"` + thêm khối `<config>` + cập nhật `EXPECTED_CONFIG_NODE_IDS` và `CONFIG_MAP` trong `unl_tool.py`, `configs/README.md`, tài liệu thiết kế.
- **Drift hiện có (2026-09-20)**: 12/51 config nhúng lệch file `configs/` — chủ yếu Brand-FW 37/38/39, SW55–60, SwitchBrand 62/63/64 (repo lưu running-config lấy từ lab ở commit `4ad720f`, còn `.unl` giữ bản dựng ban đầu); Core-SW1/2, vEdge1-S400, Switch61 chỉ khác EOL/khoảng trắng. Chưa chắc là lỗi — quyết định bản nào chuẩn rồi mới `embed`.

## Chiều đồng bộ và deploy

**Host 1 là nguồn chuẩn.** Đồng bộ **một chiều host 1 → repo**. Cấm đẩy ngược `.unl`/config từ repo lên host 1 khi người dùng chưa cho phép rõ ràng.

Khi người dùng CÓ yêu cầu Repo → EVE:
1. Xác nhận host, lab path, tenant, node-id ở môi trường hiện tại.
2. Backup `.unl` phía server sang file cụ thể trong `/tmp`; upload đúng **một** file `.unl` chính; so md5 hai phía.
3. Với từng node cần nạp lại: `/opt/unetlab/wrappers/unl_wrapper -a wipe -T 6 -F "<lab.unl>" -D <id>` rồi `-a start …` (đường dẫn đầy đủ — `unl_wrapper` không có trong PATH khi chạy qua paramiko; `-T 6` là tenant của host 1). Bỏ `-D` = cả lab (chỉ khi người dùng chủ động chấp nhận mất state).
4. Xác minh bằng prompt console, tiến trình qemu, port LISTEN, và `/opt/unetlab/tmp/6/<lab-uuid>/<id>/startup-config` — không tin exit code của wrapper.

Khi người dùng sửa trên EVE (GUI → repo): Export `.unl` → ghi đè repo → nhúng lại config nếu GUI làm mất payload → `validate` → cập nhật `configs/` lệch, `configs/README.md`, tài liệu thiết kế. Bản `.unl` lấy từ host 1 có thể có thuộc tính GUI mới (RAM, `serial`…) — chấp nhận.

**Lab UUID**: `id` ở thẻ gốc `<lab>` của `.unl` (hiện `ecf7c5b8-8c91-4616-953e-10b367b388e6`) là instance đang chạy dưới `/opt/unetlab/tmp/6/`. Từng có 2 UUID cùng tồn tại sau một lần wipe+start sai; xác định instance sống bằng `/proc/<pid-qemu>/cwd`, và chỉ start node trong đúng instance đó (start bằng `-F "<lab.unl>"` chuẩn, không wipe trước).

## Node nguy hiểm khi wipe

Wipe xoá sạch cấu hình tay + role/ứng dụng đã cài. **Không wipe**, trừ khi người dùng chốt đúng node và đã backup, các node `config="0"`: DHCP-Server 72, vManager/vSmart/vBond 33/34/35, SDN_CONTROLLER 9, OVS 5/8/66/68/69/70, Win/Mail/Web/Syslog 36/13/22/25, PC-Management 73. Sửa lỗi OVS bằng cách chạy lại script/`campus-ovs-restore`, không wipe.

`config="1"` mà **đã chỉnh tay live** (Core, ASAv, Switch32, SW…) cũng mất thay đổi chưa `write memory`/chưa nhúng khi wipe.

## Console, port, start/stop

- Console port host 1 (tenant 6) = `32768 + 128*6 + node-id` = `33536 + id` cho telnet **và** VNC (loại console ghi trong `.unl`). Riêng node 9 có serial console cấu hình riêng (port đổi theo lần start: từng 37563 → 40909 → 43495 → 33713) — đọc `ss -tlnp | grep qemu` để biết port thực. Host 2 dùng tenant 0: `32768 + id`.
- Xác minh node chạy: `ps`/`ss -tlnp`, không chỉ exit code. IOL cần Enter + chờ prompt trước khi gõ.
- Thứ tự khởi động campus: SwitchServerFarm/Core → SDN_CONTROLLER → Dist → Access. Lịch sử viosl2 từng sập vì broadcast của OVS lúc boot; với IOL không còn áp dụng nhưng vẫn nên có Core + VLAN 99 sẵn trước khi bật 6 OVS.

## Node "start im lặng" (.lock)

Wrapper trả 0 nhưng node không chạy: nguyên nhân thường là `.lock` 0-byte trong `/opt/unetlab/tmp/6/<lab-uuid>/<id>/` (status "stopped and locked": port không LISTEN + có `.lock`; `start()` chỉ chạy khi status==0). Xác minh port không LISTEN → xoá **đúng** `.lock` của node đó (đường dẫn tuyệt đối, không wildcard) → start lại → kiểm tra process/port/prompt. `cli.php` trên host 1 đã được vá tự xoá `.lock` (backup `/tmp/cli.php.bak`) nhưng bản vá mất nếu EVE cập nhật/dựng lại.

## Host 2 dự phòng (EVE 6.7.5, USB boot trong VMware)

- IP đổi theo mạng nơi đặt laptop (đã thấy 192.168.2.18 → 10.0.239.137 → 10.0.227.112): không kết nối được ≠ host chết, hỏi IP mới.
- Host 1 không với tới host 2 trực tiếp → đồng bộ qua PC trung gian (SFTP get từ host 1 → put lên host 2): tải `.unl` + thư mục node config → kiểm tra bản local (67 node / 51 `config="1"` / 51 config nhúng / 100 network) → upload → `chown -R root:root`, dir 755, file 644 → kiểm tra lại trên host 2 → **xoá thư mục tạm trên PC**.
- Khi start CLI trên host 2 dùng `-T 0` (GUI 6.7.5 quản lý ở tenant 0). Dùng `-T 6` sẽ tạo qemu song song và xung đột port.
- Image của host 2 đã đủ (asav, vios, viosl2, IOL + iourc, vtedge/vtmgmt/vtsmart/vtbond 20.10.1, win7, `linux-ubuntu-ovs-16p`, `winserver-S2012-R2-x64`…).

## Truy cập vManage GUI từ xa

Switch61 (node 61, IOL L2): `e0/0` = routed port (`no switchport` + `ip address dhcp`) nối cloud pnet0 nhận IP LAN thật (từng 10.215.28.48); `Vlan10` = 10.9.1.1/24 là gateway của vManager 10.9.1.10 / vSmart .11 / vBond .12; `ip routing` + default qua LAN thật. LAN router không biết `10.9.1.0/24`, nên:
1. Host 1 cần route: `ip route add 10.9.1.0/24 via <IP e0/0 Switch61> dev pnet0` (mất khi host reboot; IP DHCP của Switch61 có thể đổi → xem `show ip interface brief` trên console 33597).
2. Người dùng mở tunnel: `ssh -L 8443:10.9.1.10:443 root@<host1>` rồi vào `https://localhost:8443`. Cách này luôn chạy; route trực tiếp trên laptop qua VPN đã có lần không chạy — đừng đào sâu.
3. Kiểm tra nhanh vManage sống: `curl -sk https://10.9.1.10/dataservice/device` (200).

Xem thêm `HuongDan/Xem GUI Manger trên Lap.txt`.

## Bẫy hay gặp khi viết script trên host EVE

- Python trên host là **3.5**: không có `http.server --directory` (dùng `cd dir && python3 -m http.server`), không f-string.
- Chạy nền qua paramiko: `setsid nohup … </dev/null >/dev/null 2>&1 &`, nếu không sẽ chết khi channel đóng.
- **Cấm `pkill -f "chuỗi"`** khi chuỗi có trong chính command line (tự kill shell → output rỗng khó hiểu). Kill theo PID hoặc pattern có neo `^…`.
- Stderr `mesg: ttyname failed` khi `bash -lc` là vô hại.
- Không đưa mật khẩu vào command line, log, file trong repo. Script paramiko đọc mật khẩu từ file credentials cục bộ lúc chạy (hoặc biến môi trường đặt trong phiên) và không in ra. (Lựa chọn khác: Windows Credential Manager, mẫu ở `.codex/skills/campus-network-lab/scripts/eve_credential.py`.)
- Server tạm phục vụ file cho PC trong lab (ví dụ Java cho PC-Management): gán IP tạm trên `vnet6_<net>`, phải dọn (kill server, `ip addr del`, xoá file) sau khi xong.
