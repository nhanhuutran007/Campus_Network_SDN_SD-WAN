# SD-WAN Viptela 20.10.1: controller, PKI, onboarding, sự cố

Nguồn: `HuongDan/cách ký và add vedge.md`, `HuongDan/PhucHoiKetNoi_2_vEdge_Site100.txt` (xác minh 19/09/2026), `1. Tạo CSR trên thiết bị vEdge.txt`, `configs/05-Site900-*`. Không có mật khẩu ở đây — xem `console-automation.md` mục tài khoản.

## Mục lục
- Fabric và địa chỉ
- Bảng chẩn đoán: vEdge không lên controller
- Whitelist trên CẢ 3 controller
- PKI và onboard vEdge mới (9 bước)
- Định tuyến tới controller và màu TLOC
- Cấu hình vEdge lúc boot
- Lệnh kiểm tra

## Fabric và địa chỉ

- Controller site 900 (`organization-name site-900`): vManager 33 = `10.9.0.10` (+ `eth1 10.9.1.10` mặt cloud); vSmart 34 = eth0 `10.9.0.11` nhưng **system-ip `10.9.0.13`** (Viptela cấm interface IP trùng system-ip trong vpn 0 — lỗi "cannot be same in vpn 0"); vBond 35 = `10.9.0.12` local (`vbond 10.9.0.12 local`; VPN 512 eth0 `10.9.1.12`). vBond được NAT 1:1 tới `203.0.113.100` ở mặt Internet.
- Mọi vEdge: `organization-name site-900`, `vbond 10.9.0.12`, `system-ip 10.200.<site>.x`, 2 vEdge/site (Site 900 chỉ vEdge65).
- Console: `33536 + id` (vEdge 28→33564, 6→33542, 33→33569, 34→33570, 35→33571).
- vManager `sp-organization-name site-900`. Lấy `show running-config` đầy đủ bằng cách gửi `!` ở pager (không dùng space/Ctrl-L: mất phần đầu). Bản lưu: `configs/05-Site900-SDWAN-Controllers/{vManager-33,vSmart-34,vBond-35}/config.cfg`.
- Root CA thực tế của lab: **CA cũ trên vManager `/home/admin/ca/` (`root-ca.pem`/`root-ca.key`, CN `SDWAN-Lab-RootCA`)**. Controller và các edge đang chạy đều tin CA này → **ký vEdge mới bằng CA cũ**, không dùng CA v2 (`/root/sdwan-ca-v2/`, chờ dọn). Người dùng chỉ đạo: làm theo hướng dẫn 100%, không ký bằng CA khác. Ghi chú cũ "key CA mất vĩnh viễn" là SAI.

## Bảng chẩn đoán: vEdge không lên controller

Bắt đầu bằng `show control connections-history` trên vEdge (manh mối rõ nhất), `show control local-properties`, `show certificate installed`, `show clock`.

| Dấu hiệu | Nguyên nhân | Xử lý |
|---|---|---|
| `BIDNTVRFD` / `RXTRDWN` / `ERR_BID_NOT_VERIFIED`; log controller `serial number not found in vedge-list` | Serial vEdge **không có trong whitelist** của controller (DB whitelist là **runtime**, mất khi reboot controller; nhánh này gây sự cố 05/09 và 19/09) | `request vedge add` trên cả 3 controller — **không** reboot/wipe gì. Vài phút sau vEdge tự retry DTLS (~16 s/lần) |
| Log `Peer's Certificate validation Failed (expected Viptela) got "…"` | Subject cert có **O ≠ "Cisco Systems"** | Ký lại cert với subject chuẩn (mục PKI) |
| `unable to get local issuer certificate` | Thiếu `request root-cert-chain install` | Cài root chain rồi cài cert |
| vEdge chỉ lên vbond + vmanage, `vsmart_counts 0` | Chưa whitelist ở **vSmart** | `request vedge add` trên vSmart |
| GUI "1/3 vsmart", 1 màu WAN kẹt `connect/DCONFAIL` | Route tới controller LAN chỉ có 1 ngả (longest-prefix che ngả kia) | Mục "Định tuyến tới controller" |
| `vdaemon_disable_my_tloc`, "interface not configured yet" | Config tunnel đẩy **sau** khi vdaemon chạy | Mục "Cấu hình vEdge lúc boot" |
| Không ping được controller từ vEdge | Route/BGP/ACL underlay | `ping vpn 0 source <ip-wan> 10.9.0.12`, kiểm `show ip route vpn 0` |

Một vEdge "khỏe" giữ phiên cũ nên không lộ lỗi whitelist — nếu nó reboot sẽ rơi giống hệt. Vì vậy sau reboot controller luôn kiểm tra whitelist đủ 8 vEdge.

## Whitelist trên CẢ 3 controller

Thiếu một nơi là không lên controller đó. Lệnh giống hệt trên vManager (33569), vBond (33571), vSmart (33570):

```
request vedge add chassis-num <uuid> serial-num <40-hex>
```

- `chassis-num` và `serial-num` lấy từ `show control local-properties` trên vEdge **tại thời điểm hiện tại**. Serial đổi mỗi lần ký lại cert; add serial mới sẽ ghi đè entry theo chassis (không cần xoá cũ; `request vedge remove` không có).
- Kết quả đúng: `status success`. Kiểm: vManager/vSmart `show control valid-vedges`; **vBond dùng `show orchestrator valid-vedges`** (nếu dùng lệnh kia sẽ báo "No entries found" dù đã add). Cần đủ 8 entry, org `site-900`.
- vManager còn có danh sách whitelist qua API (`certificate/vedge/list`) khác với `valid-vedges` CLI — vẫn phải add bằng CLI.
- Lệnh trên vBond/vSmart thường không có `vshell`; đọc log bằng `show log messages`.

## PKI và onboard vEdge mới (9 bước, đã chạy đủ 3 controller trên node 6)

Dùng cho vEdge mới, sau wipe/re-image, hoặc khi mở rộng chi nhánh (đổi `host-name/system-ip/site-id`).

1. **Baseline config** (từ `configs/<site>/<vEdge>/config.cfg`) qua console: `host-name`, `system-ip`, `site-id`, `organization-name site-900`, `vbond 10.9.0.12`, hai WAN `tunnel-interface encapsulation ipsec color …`, `boot bfd`, `security ipsec`, `omp`. **Đừng bỏ/`no` `vpn 0 interface eth0`** (gây lỗi commit). Cổng WAN (`ge0/2`, `ge0/3`…) thay đổi theo từng vEdge — lấy từ file cấu hình của đúng vEdge.
2. **Route tới controller LAN** trong `vpn 0` (mục dưới) — cần để scp/DTLS trước khi BGP học default.
3. **Tạo CSR**: `request csr upload /home/admin/<hostname>.csr`. Chỉ hỏi *organization-unit* (2 lần) → nhập **`site-900`**; các trường khác lấy mặc định hãng. Trước khi ký kiểm: `openssl req -noout -subject -in <file>.csr`.
4. **Chuyển CSR lên vManager (là CA)**: `request execute vpn 0 scp /home/admin/<hostname>.csr admin@10.9.0.10:/home/admin/ca/<hostname>.csr` (yes cho host-key, nhập mật khẩu). **Cấm URL dạng `scp://user@ip:22/…`** — Viptela hiểu `:22` là thư mục `~/22/`.
5. **Ký bằng CA cũ trên vManager** (`vshell` → `cd /home/admin/ca`):
   `openssl x509 -req -in <hostname>.csr -CA root-ca.pem -CAkey root-ca.key -CAcreateserial -out <hostname>.crt -days 730 -sha256`
   Subject **phải** là `C=US, ST=California, L=San Jose, OU=site-900, O=Cisco Systems, CN=vedge-<uuid>-<N>.viptela.com/emailAddress=support@viptela.com` — vBond/vSmart **từ chối O khác** (vd "VNPT") và đây là root cause khiến node 6 kẹt "connect" cả ngày.
6. **Kéo cert + root CA về vEdge** (scp ngược chiều): `…scp admin@10.9.0.10:/home/admin/ca/<hostname>.crt /home/admin/` và `…root-ca.pem /home/admin/`.
7. **Cài chain trước, cert sau**: `request root-cert-chain install /home/admin/root-ca.pem` → `request certificate install /home/admin/<hostname>.crt`. Kiểm `show control local-properties`: `cert-validity Valid`, root-cert-chain OK.
8. **Whitelist cả 3 controller** (mục trên).
9. **Xác minh**: `show control connections` (vbond + vmanage + vsmart Up), `show control summary` (vbond/vmanage/vsmart counts), vManage `/dataservice/device` = reachable/normal.

Với 2 màu WAN kỳ vọng `vbond_counts 2 / vsmart_counts 2 / vmanage_counts 1` (vManage chỉ cần một phiên, không theo màu) và `valid_controller_counts 2`.

## Định tuyến tới controller và màu TLOC

- Controller LAN `10.9.0.0/24`. vEdge Site 100 học default qua BGP, nhưng khi chưa onboard cần **static** trong `vpn 0`. Bài học 05/09: có cả `10.9.0.0/16 via <SP-biz>` và `10.9.0.0/24 via <SP-mpls>` thì `/24` (mpls) thắng, che ngả biz → màu `biz-internet` không có egress cho DTLS → GUI "1/3 vsmart". **Sửa: thêm cùng prefix `/24` qua ngả biz (ECMP)**. Tổng quát: mỗi ngả transport cần route đủ cụ thể, không chỉ `/16` chung.
- **Màu TLOC phải khớp transport**: WAN Internet (203.0.113.x) → `biz-internet`; WAN MPLS (100.64.x) → `mpls`. Khai nhầm `mpls` trên WAN Internet (vEdge2-S200/300/400, sửa 30/08) làm mọi tunnel biz↔mpls Down. Kiểm `show omp tlocs`, `show bfd sessions`.
- Underlay là **BGP** (Internet AS 64511 ↔ MPLS AS 64512; site 65000/65010/65020/65030 eBGP CE-PE dưới `vpn 0`, `default-originate` từ SP). vEdge không còn `ip route 0.0.0.0/0` (học default qua BGP), riêng vEdge1/2-S100 giữ `100.64.0.0/8` dự phòng phía MPLS. Site 900 static.

## Cấu hình vEdge lúc boot

vtedge = qemu; disk `/opt/unetlab/tmp/6/<lab-uuid>/<id>/virtioa.qcow2`, template `/opt/unetlab/addons/qemu/vtedge-20.10.1/virtioa.qcow2` (~409 MB). **`vdaemon` chỉ nhận `tunnel-interface` khi config đã có LÚC BOOT** (dán CLI sau khi vdaemon chạy không ăn).

Wipe thủ công (chỉ khi được phép): kill qemu theo **PID** (cấm `pkill -f`) → `rm` disk → `cp` từ template → `chown unl6:unl`, `chmod 664` → ghi `startup-config` **đầy đủ** (hostname + hash mật khẩu + tunnel-interface) vào thư mục node → start bằng `unl_wrapper` → boot **10–15 phút** tới `vedge login:` (console hay chỉ hiện ANSI title, gửi Enter). Sau wipe mật khẩu mặc định và bắt buộc đổi (nhập cùng giá trị 2 lần). Nếu `config_vtedge.py` timeout do boot > 300 s, chạy thủ công khi đã thấy `login:` và kiểm running-config. Trước khi kết luận `vdaemon` lỗi, loại trừ theo thứ tự: đồng hồ (`show clock`), chứng chỉ/root chain, whitelist, route/underlay.

## Lệnh kiểm tra

vEdge: `show control summary`, `show control connections`, `show control connections-history`, `show control local-properties`, `show certificate installed`, `show bfd summary`/`sessions`, `show omp peers`/`tlocs`, `show ip route vpn 0`, `show ip bgp summary`.
Controller: `show control valid-vedges` (vManager/vSmart), `show orchestrator valid-vedges` (vBond), `show log messages`.
SP (IOS): `show ip bgp summary`, `show ip bgp`.
