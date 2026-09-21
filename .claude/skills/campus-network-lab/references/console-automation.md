# Điều khiển thiết bị qua console

Chỉ thực hiện khi người dùng đã yêu cầu tác động lên lab. Không đưa mật khẩu vào script/log/lệnh; lấy từ file credentials cục bộ (mục "Quy tắc tài khoản" bên dưới), không in ra.

## Mục lục
- Quy trình mở console an toàn
- Khung code (telnet qua paramiko)
- Hành vi theo nền tảng
- Console VNC và gõ phím tự động
- Quy tắc tài khoản
- Kiểm tra hoàn tất

## Quy trình mở console an toàn

1. Xác nhận host EVE, lab, tenant, node-id; lấy port **thực** bằng `ss -tlnp | grep qemu` (công thức `33536 + id` chỉ là gợi ý). Từ máy Windows thường không chạm trực tiếp cổng console được → dùng SSH tới host EVE rồi mở kênh **`direct-tcpip`** tới `127.0.0.1:<port>` (paramiko `transport.open_channel("direct-tcpip", ("127.0.0.1", port), ("127.0.0.1", 0))`).
2. Gửi Enter, **chờ prompt ổn định** rồi mới gửi lệnh đầu. Lệnh gõ ngay khi kênh mở sẽ bị nuốt im lặng (IOL/vIOS chưa sẵn sàng). Nếu ra initial-config dialog → trả lời `no` NGAY (console IOL không phát lại màn hình cũ; lệnh khác bị nuốt bằng "% Please answer 'yes' or 'no'").
3. Tắt pager (`terminal length 0` / `screen-length 0`). Gửi từng dòng, chờ 0,3–0,5 s; tăng thời gian cho sinh khoá/commit/save.
4. Dùng **marker** để biết lệnh xong (`; echo __DONE_<ts>__` trên Linux; chờ prompt trên Cisco/Viptela) thay vì `sleep` cố định. Một shell gõ nhiều lệnh liên tiếp dễ vượt timeout 120 s của công cụ → tách thành cụm nhỏ hoặc chạy nền rồi đọc log.
5. Thu output, tìm lỗi cú pháp, rồi đọc lại running state. Gửi hết chuỗi lệnh ≠ thành công.
6. Lưu đúng cách (`write memory` / `commit`). Nếu phiên đang kẹt ở config mode gõ `end` trước `show`.
7. Đóng channel + SSH client trong `finally`. Console vEdge chỉ cho **1 session**: nếu người dùng đang mở console trong EVE GUI thì agent không gửi được — nhờ họ đóng.

## Khung code (telnet qua paramiko)

```python
import re, time, paramiko

ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")
def clean(b): return ANSI.sub(b"", b.replace(b"\x00", b""))

def open_console(ssh, port):
    ch = ssh.get_transport().open_channel("direct-tcpip", ("127.0.0.1", port), ("127.0.0.1", 0))
    ch.settimeout(0.5)
    return ch

def drain(ch, quiet=1.2, limit=30):
    buf, last, t0 = b"", time.time(), time.time()
    while time.time() - last < quiet and time.time() - t0 < limit:
        try:
            d = ch.recv(65535)
            if d: buf += d; last = time.time()
        except Exception:
            pass
    return clean(buf).decode("utf-8", "replace")

def send(ch, line, wait=0.4):
    ch.send(line + "\r"); time.sleep(wait); return drain(ch, quiet=wait + 0.6)
```

Đăng nhập Viptela/Linux: drain tới `login:` → gửi user → drain tới `Password:` → gửi mật khẩu → drain tới prompt. Nhận `Login incorrect` thường do gửi sai trình tự, đừng vội kết luận sai mật khẩu (login sai nhiều lần → khoá tài khoản ~15 phút).

Ví dụ hoàn chỉnh: `inspect_dist_console.py` ở gốc repo (telnet + marker + đăng nhập `eve@ovs`; file chưa track).

## Hành vi theo nền tảng

| Nền tảng | Khởi tạo | Lưu / xác minh | Lưu ý |
|---|---|---|---|
| IOL IOS | Enter → `enable` → `terminal length 0` | `write memory`; `show vlan brief`, `show interfaces trunk` | `switchport trunk encapsulation dot1q` **trước** `switchport mode trunk`; `vtp mode off` **trước** khối `vlan`; config nén khi lưu (running ≈1276 B → nvram ≈813 B) |
| ASAv | chờ prompt → `enable` | `write memory`; `show failover`, `show dhcpd state` ("Configured for DHCP SERVER") | Lần đầu "enable password is not set" → gửi mật khẩu 2 lần (chờ console idle ~1,2 s giữa hai lần). HA: config tự replicate, đừng cấu hình như hai máy độc lập |
| vIOS (Internet/MPLS) | Enter để thoát màn hình ANSI; `terminal length 0` | `write memory` | Phải `terminal length 0` (phím `!` chỉ thoát pager trên Viptela). `ip address dhcp` kẹt ("DHCP is already running") → không gỡ; phải wipe+start đúng node. `default-originate` trong address-family |
| vEdge/Viptela | chờ `login:` (console hay chỉ hiện ANSI title → gửi Enter) | `commit`; `show control connections`, `show running-config` | `screen-length 0`. Lấy config dài: pager `--More--` gửi `!` (không dùng space/Ctrl-L). Không để config dở chưa commit. Chi tiết: `sdwan-viptela.md` |
| VPCS | chờ `VPCS>` | `ip dhcp` rồi `ip` | `ip dhcp` in menu help = đã có IP; chỉ `ip` mới là kết quả quyết định. DHCP server phải boot xong |
| Linux/OVS, controller | serial telnet (node 9) hoặc VNC | `ovs-vsctl show`, `ovs-ofctl -O OpenFlow13 dump-flows br0` | Không mở SSH (probe :22 CLOSED) — mọi thao tác qua console |
| Windows | VNC/GUI | kiểm tra IP, service, firewall | Node `config="0"`; GUI do người dùng làm |

Bảng lệnh kiểm tra nhanh: IOL `show vlan brief` / `show ip route` / `show ip ospf neighbor` / `show ip bgp summary`; ASAv `show failover state` / `show interface ip brief` / `show asdm sessions`; vEdge `show control connections` / `show bfd summary` / `show omp peers`.

## Console VNC và gõ phím tự động

Các node Linux OVS/Windows dùng VNC; SSH tới OVS và node 9 **đóng**. Đường duy nhất là VNC (hoặc serial của node 9), đã rút ra:

- `vncdotool` **không gõ được** `|`, `>`, `&` (lệnh có pipe/redirect bị hỏng, OCR thấy `sudo -S ovs-vsctl show bro`…). Gõ lệnh chỉ gồm ký tự thường/khoảng trắng; dùng `sudo -S <cmd>` tương tác (gõ lệnh → Enter → chờ → gõ mật khẩu → Enter → chụp màn hình).
- Từng gặp gõ phím ra **CHỮ HOA toàn bộ** (10/08): thử giữ Shift khi gõ, cờ `--force-caps`, hoặc kiểm tra keymap trong VM. Trên PC Win7 gõ phím qua VNC không có tác dụng → thao tác GUI do người dùng làm.
- Đưa file lớn vào node không SSH: **heredoc + base64**: nén `gzip`, `base64` chia dòng, gõ `cat > /tmp/x.b64 <<'EOF' … EOF` qua VNC/serial, rồi `base64 -d | gzip -d > file` → `chmod` → `md5sum` → in marker (`VERIFY-DONE`). Với 177 dòng đã gõ được qua VNC cho node 9. Không có kênh md5 byte-exact tự động → so md5 đích với md5 ground-truth tính từ file trong repo.
- Đọc màn hình: chụp VNC → OCR (Windows.Media.Ocr hoặc `pytesseract` + tesseract 5.x, phóng ảnh ×3, `--psm 6`). OCR nhiễu với hex dài (md5) — đừng lặp vòng OCR tốn công; tin marker + md5 ground-truth.
- Serial console của node 9 hay có ký tự `\x00`/ESC → dùng `clean()` ở trên.
- Nếu EVE host mất kết nối giữa chừng: đừng kết luận node hỏng; kiểm tra host trước (ping/SSH, WLAN, gateway) và chờ host lên lại.

## Quy tắc tài khoản

- **Mật khẩu ở `C:\Users\nhanh\.claude\campus-lab-credentials.md`** (cục bộ, ngoài repo). Đọc file đó để lấy đúng mật khẩu theo thiết bị, **không hỏi lại người dùng**; script đọc file lúc chạy (không nhúng cứng, không đưa lên command line, không in ra output).
- Có **nhiều họ tài khoản khác nhau** — đừng dùng chung: ASAv (enable + admin), vEdge Site 100, vEdge chi nhánh (Site 200/300/400 + vEdge65), vManager, vBond, vSmart, Linux OVS/controller (`eve`), host EVE (root). File credentials có bảng theo node-id.
- vEdge từ chối mật khẩu có 3 ký tự lặp/liên tiếp ASCII (`abc`, `123`, `aaa`); lúc đặt mật khẩu lần đầu phải nhập **cùng một giá trị** ở `Password:` và `Re-enter password:`.
- Sau khi wipe vEdge mật khẩu là mặc định của hãng và bắt buộc đổi ngay.
- Login sai liên tiếp → tài khoản khoá ~15 phút. Chỉ thử đúng mật khẩu đã ghi cho thiết bị đó; sai một lần thì dừng, đối chiếu file credentials/hỏi người dùng thay vì thử mò họ khác. Khi người dùng cho mật khẩu mới hoặc đổi mật khẩu, cập nhật vào file credentials.

## Kiểm tra hoàn tất

Prompt/output live chứng minh thiết bị chấp nhận cấu hình; đã `write memory`/`commit`; VLAN/trunk/route/lease/control connection liên quan được kiểm bằng lệnh `show`; không đụng node ngoài phạm vi; không để bí mật trong transcript/repo. Việc chưa xác minh được (GUI, cần EVE thật) phải nêu rõ, không báo "xong" theo suy đoán.
