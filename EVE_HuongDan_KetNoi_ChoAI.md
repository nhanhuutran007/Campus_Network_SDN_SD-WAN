# Hướng dẫn kết nối EVE host 1 và cấu hình thiết bị (cho AI)

Hướng dẫn này dành cho AI (agent) được giao việc cấu hình thiết bị trên lab EVE-NG của đồ án. Đọc thêm: `configs/README.md` (bảng node-id đầy đủ), `campus_network_sdn_sdwan.md` (thiết kế + quy ước IP).

## 1. Kết nối SSH vào EVE host 1

```python
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("10.215.28.26", username="root", password="<pass do người dùng cấp từng phiên>")
stdin, stdout, stderr = ssh.exec_command("ls /opt/unetlab/labs/TranHuuNhan-PKT/")
print(stdout.read().decode())
```

- Host 1: `root@10.215.28.26` — password do người dùng cấp mỗi phiên, **không lưu vào file, không in ra log**.
- Lab path: `/opt/unetlab/labs/TranHuuNhan-PKT/Campus Network SDN SD-WAN.unl`

## 2. Start / wipe node qua CLI (thay cho GUI)

```bash
/opt/unetlab/wrappers/unl_wrapper -a wipe -T 6 -F "/opt/unetlab/labs/TranHuuNhan-PKT/Campus Network SDN SD-WAN.unl" -D <node-id>
/opt/unetlab/wrappers/unl_wrapper -a start -T 6 -F "/opt/unetlab/labs/TranHuuNhan-PKT/Campus Network SDN SD-WAN.unl" -D <node-id>
```

- **`-T 6` bắt buộc trên host 1** (tenant 6); `-D <id>` để chỉ 1 node; bỏ `-D` = toàn lab.
- **QUAN TRỌNG**: EVE chỉ nạp config từ **phần nhúng base64 trong `.unl`** (`<configs><config id="N">base64</config>`). File `config.cfg`/`config.txt` trong thư mục node trên server KHÔNG được EVE đọc khi start — chỉ dùng để paste tay. Vì vậy khi sửa config: cập nhật cả `configs/<id>/...` trong repo VÀ phần nhúng trong `.unl` (dùng python xml.etree), verify `config="1"` = 51 node.
- Console port: IOL/ASAv/vEdge = `33536 + <node-id>`; qemu VNC = `32768 + <node-id>`.

## 3. Cấu hình thiết bị qua console (telnet)

```python
import telnetlib
tn = telnetlib.Telnet("10.215.28.26", 33536 + <node-id>)
```

- **IOL** (Core-SW1/2, SwitchBrand, switch phòng ban): kết nối xong phải gửi Enter rồi chờ prompt `>`/`#` trước khi gõ lệnh đầu (gõ sớm → mất lệnh im lặng). Sau đó: `enable` → `terminal length 0` → `configure terminal` → dán config → `write memory`.
  - Bắt buộc trong config: `vtp mode off` TRƯỚC khối `vlan`; `switchport trunk encapsulation dot1q` TRƯỚC `switchport mode trunk` (nếu không → "Command rejected: trunk encapsulation Auto").
- **ASAv** (FW-ASAv, Brand-FW): `enable` → nếu lần đầu "enable password is not set" → gửi password ×2 (chờ mỗi lần console idle ~1.2s — drain-timing) → `configure terminal` → dán config → `write memory`. Verify: `show dhcpd state` = "Configured for DHCP SERVER", `show interface ip brief`.
- **VPC**: gõ `ip dhcp` rồi `show ip`. Nếu `ip dhcp` hiện menu help = đã có IP.
- **vEdge**: xem mục 4.

## 4. vEdge — đẩy config LÚC BOOT (điểm đặc biệt)

`vdaemon` **chỉ nhận tunnel-interface khi config được đẩy LÚC BOOT, trước khi vdaemon khởi động** — paste qua CLI sau khi vdaemon chạy thì không ăn (log: "But interface not configured yet" + "vdaemon_disable_my_tloc").

Quy trình:

1. Wipe node: `kill -9 <PID qemu>` (**CẤM `pkill -f`** — pattern match cmdline của chính shell → tự kill), `rm` disk, `cp` image gốc → disk, `chown unl6:unl` + `chmod 664`.
   - Image gốc: `/opt/unetlab/addons/qemu/vtedge-20.10.1/virtioa.qcow2` (409MB); disk: `/opt/unetlab/tmp/6/<lab-uuid>/<node-id>/virtioa.qcow2`.
2. Ghi startup-config ĐẦY ĐỦ (hostname + password hash + tunnel-interface) vào `/opt/unetlab/tmp/6/<lab-uuid>/<node-id>/startup-config`.
3. Start node → boot 10–15 phút → `vedge login:` → `admin` + password → `config` → dán từng dòng config → `commit` → `end`.
4. Sau wipe password là admin/admin + bắt buộc set password mới (gõ password ×2 khi gặp `Password:`/`Re-enter password:`).
5. Console vEdge chỉ cho **1 session** — nếu người dùng đang mở console EVE GUI thì agent không gửi lệnh được; nhắc người dùng đóng console khi agent làm việc.

## 5. Verify sau cấu hình

- Console port thực tế: `ss -tlnp | grep qemu` trên host.
- Config thực tế node nạp: `/opt/unetlab/tmp/6/<lab-uuid>/<node-id>/startup-config`.
- Lệnh kiểm tra: IOL `show vlan brief` / `show ip route` / `show ip ospf neighbor`; ASAv `show dhcpd state` / `show interface ip brief`; vEdge `show control connections` / `show running-config` / `show system status`.

## 6. Quy tắc quan trọng

- **Sửa config → đồng bộ 3 nơi**: file `configs/<dir>/` trong repo + phần nhúng base64 trong `.unl` + dán tay lên lab (nếu cần live).
- Sau khi sửa `.unl`: kiểm tra XML hợp lệ (python xml.etree), đếm `config="1"` = 51 node đúng danh sách (xem configs/README.md).
- Đồng bộ repo ↔ EVE: SCP ghi đè DUY NHẤT file `.unl` lên host 1, backup trước (`cp .../*.unl /tmp/unl.backup`), rồi wipe + start qua CLI.
- **CẤM**: chu kỳ Delete lab → Import lại (mất config nhúng); mở/save lab qua GUI EVE (reset cờ `config="1"` → 0).
- Password thiết bị: xem `configs/README.md` (ASDM mục PC-Management, controller mục 15/08/2026) — không ghi mật khẩu mới vào file repo.