# Campus NetOps Bot — ChatOps/MCP cho lab Campus Network SDN + SD-WAN

Bản sao của dự án [Netmiko-MCP-Telegram](https://github.com/nhanhuutran007/Netmiko-MCP-Telegram) (Trần Hữu Nhân), được điều chỉnh để vận hành lab EVE-NG của đồ án. Bản gốc giữ nguyên ở repo riêng.

Người vận hành hỏi bằng ngôn ngữ tự nhiên qua Telegram, terminal hoặc MCP (Claude Desktop / MCP Inspector), ví dụ *"BFD của vEdge1-S300 có đủ phiên không?"*. Agent LangGraph (LLM chuẩn OpenAI: OpenRouter mặc định, đổi được sang Google AI Studio qua `.env`) chọn thiết bị, chạy lệnh qua console EVE-NG rồi tóm tắt kết quả.

## Giai đoạn 1 (đã xong): nền tảng chỉ đọc

| Thành phần | Nội dung |
|---|---|
| `campus/inventory.py` | Danh mục 47 thiết bị theo site/vai trò/nền tảng. Tên duy nhất như `vEdge2-S200` (node 42), khoá thật là node-id. `verify_against_unl()` đối chiếu với `.unl` |
| `campus/console.py` | Chạy lệnh qua **console EVE** (SSH tới server EVE → `direct-tcpip` tới cổng `32768 + 128·tenant + node-id`). Không cần IP quản trị, nên vẫn vào được khi mất VLAN 99 |
| `campus/guard.py` | **Chỉ cho** `show` / `ping` / `traceroute`. Chặn cấu hình, `reload`, `clear`, `copy`, `\| redirect`, xuống dòng, `;`, `show tech`, ping tương tác |
| `campus/redact.py` | Che `password/secret/key/community/$6$…` trước khi gửi output cho LLM, Telegram hay NetBox |
| `campus/credentials.py` | Đọc mật khẩu từ file Markdown cục bộ, ngoài repo (`CAMPUS_CRED_FILE`). LLM không bao giờ thấy mật khẩu |
| `campus/service.py` | API chung cho agent, MCP và Telegram; lỗi báo bằng cờ `ok`, không đoán theo chữ "error" |

Nền tảng hỗ trợ: IOS/IOL (Core, SwitchBrand, SW, Switch32…), vIOS (Internet, MPLS), ASAv (FW HA, Brand-FW), Viptela (vEdge, vManage, vSmart, vBond). OVS, Linux, VPCS và Windows mới chỉ được liệt kê; điều khiển chúng thuộc giai đoạn sau.

### Thay đổi so với bản gốc

- Không còn `.env` trong mã nguồn; dùng `.env.example`. File mẫu `Mau/netbox_devices.csv` đã che mật khẩu.
- Telegram chỉ phục vụ `TELEGRAM_ALLOWED_CHAT_IDS`. Có thêm lệnh trực tiếp `/devices`, `/show`, `/ping` không qua LLM, và tin dài được chia nhỏ theo giới hạn 4096 ký tự.
- Tool MCP nhận **tên thiết bị**, không còn nhận `USERNAME/PASSWORD`.
- Sửa lỗi bản gốc báo "Lỗi" với mọi output chứa chữ `error`/`fail` (như `show interfaces`).
- `AgentCiscoClient` không còn dùng chung dict kết nối giữa các request đồng thời.
- NetBox không còn chứa mật khẩu (bỏ custom field `ssh_password`); backup cấu hình được che bí mật.
- Console: mỗi node chỉ một phiên tại một thời điểm. Bot dừng khi gặp config mode hay initial dialog (không gõ đè lên người đang thao tác), và dừng ngay khi `Login incorrect` (tránh khoá tài khoản vEdge 15 phút).

## Giai đoạn 2 (đã xong): cảnh báo chủ động + chẩn đoán theo lớp

| Thành phần | Nội dung |
|---|---|
| `campus/tunnel.py` | Forward cổng cục bộ tới dịch vụ trong lab qua SSH của server EVE: vManage `10.9.1.10:443`, Ryu `:8080` |
| `campus/labapi.py` | Client REST chỉ đọc. **vManage**: đăng nhập `j_security_check` + XSRF token, `device`, `alarms` (lọc bỏ `cpu-usage`/`memory-usage`, chiếm hơn 90% alarm của lab). **Ryu**: `/campus/health`, `/stats/switches`, `/stats/flow/<dpid>` |
| `campus/diagnose.py` | Chẩn đoán theo lớp, **dừng ở lớp lỗi đầu tiên**, có bằng chứng và gợi ý sửa lấy từ kinh nghiệm đồ án (màu TLOC, NIC ảo treo, whitelist, `dot1q` trước `mode trunk`…) |
| `campus/alerts.py` | `AlertMonitor`: alarm vManage mới (theo uuid; lần đầu chỉ ghi nhớ, không gửi dồn), vManage mất/khôi phục (đây là kế hoạch B của mail cảnh báo: vẫn báo khi chính vManage chết), OVS mất/nối lại controller, link OVS chết/sống, Ryu khựng ≥ 6 s. Có "Tắt 1 giờ" và lưu trạng thái ra file |

Các bài chẩn đoán:

| `/diag …` | Các lớp |
|---|---|
| `vEdge1-S300` (mọi vEdge) | L1 cổng transport VPN 0 → L3 BGP underlay → default route → control connections → OMP → BFD overlay |
| `dhcp 200` / `300` / `400` | L2 trunk SwitchBrand → L3 gateway sub-interface Brand-FW → dhcpd → lease |
| `dhcp 100` | L2 SDN (Ryu: OVS + link) → L3 SVI Core-SW1 → relay `ip helper-address` → ping DHCP-Server 10.1.90.10 |
| `sdn` | Kênh OpenFlow 6/6 → link 13/13 → dự phòng VLAN 99 → controller khựng |

Ví dụ thật (29/10/2026):

```
🩺 Chẩn đoán vEdge1-S300 (node 30, site 300)
✅ L1 Giao diện WAN: ge0/0 100.64.30.1/30 Up
✅ L3 Underlay BGP: 1/1 neighbor established
✅ L3 Default route VPN 0: 0 0.0.0.0/0 bgp e ge0/0 100.64.30.2 - - - - F,S
✅ Dịch vụ: Control connections: vSmart 1, vManage 1, vBond 1
✅ Dịch vụ: OMP: vSmart 10.9.0.13 up R/I/S 15/8/3
✅ Overlay BFD: 4/4 phiên up, tới site 200, 400
```

Cảnh báo trên Telegram có dạng `🔴 BFD_Node_Down — vEdge2-S200`, kèm nút **🩺 Chẩn đoán vEdge2-S200** (chạy bài chẩn đoán ngay) và **🔕 Tắt 1 giờ**.

**Điều kiện mạng:**
- vManage `10.9.1.10` đi qua Switch61 (node 61). Server EVE cần route `10.9.1.0/24 via <IP e0/0 của Switch61>`. IP này lấy bằng DHCP nên có thể đổi; route mất khi reboot.
- Ryu: đặt `SDN_CTL=http://<IP ens6 node 9>:8080`. Tìm IP trên server EVE bằng `ip neigh | grep -i 50:00:00:09:00:03`. Firewall `CAMPUS_ENS6` của node 9 phải cho phép IP server EVE.

## Giai đoạn 3 (đã xong): thay đổi có duyệt + tự rollback, tuân thủ, drift

| Thành phần | Nội dung |
|---|---|
| `campus/change.py` | Vòng đời yêu cầu: propose → **Duyệt** → áp → kiểm → (đạt: lưu / xấu đi: rollback) → hoàn tác trong 1 giờ. Audit log dạng JSON Lines (`audit.log`) |
| `campus/health.py` | Ảnh chụp trước/sau. **IOS**: interface up/up, BGP established, OSPF FULL, VRRP. **Viptela**: transport up, BGP, control vSmart/vManage, BFD up. Mất bất kỳ mục nào có từ trước là KHÔNG ĐẠT |
| `campus/compliance.py` | Bất biến thiết kế: Core relay `10.1.90.10` + VRRP `.1` cho VLAN 10–40; Brand-FW pool `.100–.199` + `dhcpd enable`; vEdge `site-id`, System-IP `10.200.<site>.x`, màu TLOC khớp transport; router Internet có `NO_DEFAULT_IN` cho mọi khách hàng (thiếu dòng này là nguyên nhân sự cố 25/10) |
| `campus/drift.py` | `/backup`: lưu running-config đã che bí mật vào `backups/<thời điểm>/`, so với `configs/` (bỏ dòng nhiễu, timestamp, dòng bí mật) |

Rollback theo nền tảng (đã thử live 29/10/2026):

| Nền tảng | Điểm khôi phục | Áp | Rollback tự động | Hoàn tác |
|---|---|---|---|---|
| IOS/IOL, vIOS | `copy running-config unix:` (IOL) / `flash:` (vIOS) `netops-<id>.cfg` | `configure terminal` từng dòng | `configure replace <file> force` | như rollback + `write memory` |
| Viptela | không cần — `config exclusive` + `commit confirmed 5` | commit confirmed | `commit abort` (bot chết giữa chừng thì vEdge tự quay lại sau 5 phút) | `rollback configuration 0` + `commit` (chỉ khi chưa có commit khác) |
| ASA | — | **chưa hỗ trợ**: bot từ chối, agent chỉ đưa lệnh để làm tay | | |

Rào an toàn:
- **LLM không tự áp được**: tool `propose_change` chỉ tạo yêu cầu, người bấm **Duyệt** mới chạy. MCP chỉ soạn khối `/change` để dán vào Telegram.
- Chặn `reload`, `write`, `copy`, `erase`, `do`, `end`, `configure`, `clear`, `username`, `enable secret`, `password`, `secret`, `snmp community`, `no router bgp|ospf`, `no vpn 0`; với Viptela chặn thêm `commit`, `rollback`, `system-ip`, `site-id`, `organization-name`, `vbond`. Tối đa 40 dòng mỗi yêu cầu.
- Yêu cầu chờ duyệt hết hạn sau 10 phút. `CHANGE_APPROVER_IDS` giới hạn người được duyệt; `CHANGE_FOUR_EYES=1` bắt buộc người duyệt khác người yêu cầu. Nút Duyệt bị gỡ ngay khi bấm để tránh chạy hai lần.

Kết quả thử live:

| Ca | Thiết bị | Kết quả |
|---|---|---|
| Thêm Loopback99 → hoàn tác | SW-S500 (IOL) | `done` (5 interface up/up) → `undone`, Loopback99 không còn |
| Dòng sai cú pháp | SW-S500 | `% Invalid input` → `configure replace` → `rolled_back`, sức khoẻ như trước |
| `shutdown` Ethernet0/1 | SW-S500 | kiểm sau: mất `Ethernet0/1` → `rolled_back`, cổng up lại |
| `system location` → hoàn tác | vEdge2-S300 | commit confirmed → BFD 4/4, control 2 → `commit` → `rollback configuration 0` (lịch sử commit có `netops-ac7804`, `netops-undo-ac7804`) |
| Dòng sai cú pháp | vEdge2-S300 | `syntax error` → `abort`, không commit |
| `reload`, `username …`, ASA | — | bị chặn ngay từ bước kiểm lệnh |
| `/compliance all` | thiết bị đang chạy | Internet 7/7, 6 vEdge chi nhánh đạt |
| `/backup all` | 13 thiết bị đang chạy | lệch thật: Switch32 (cổng vEdge-Spare2, thứ tự ACL 587), Switch61 (`clock timezone`) |

Cách dùng trên Telegram:

```
/change SW-S500
# lý do: thêm loopback quản trị
interface Loopback99
 description netops
```

Bot trả về thẻ (dòng `+` là mới, `=` là đã có) kèm nút ✅ Duyệt / ❌ Huỷ. Sau khi duyệt, tiến trình cập nhật trực tiếp trong một tin nhắn, và kết quả kèm nút ↩️ Hoàn tác. Lệnh khác: `/changes`, `/approve <id>`, `/cancel <id>`, `/undo <id>`, `/compliance [all|200|Core-SW1]`, `/backup [all|site|thiết bị]`, `/drift <thiết bị>`. Ngoài Telegram có `python scripts/change_cli.py <thiết bị> "<dòng>" … --reason "…"`, quy trình giống hệt và phải gõ `yes` để duyệt.

## Triển khai thực tế: NetOps-Server trong topo (in-band)

Bot chạy **bên trong mạng Campus** trên DHCP-Server (node 72, `10.1.90.10`, Server Farm) như một máy chủ hạ tầng, và quản trị thiết bị bằng **SSH qua mạng quản trị**. Bot không có quyền vào server EVE.

```
 Telegram / LLM OpenRouter (Internet)
        ▲ chỉ TCP 443 đi ra — luật FW sẵn có: permit 10.1.90.0/24 any eq https
   FW-ASAv HA ── vEdge Site 100 (DIA)
        │
   Core-SW1 10.1.90.2 / Core-SW2 10.1.90.3 (VRRP 10.1.90.1)
        │                       └─ Vlan99 10.1.99.1 ── SwitchServerFarm 10.1.99.32, Ryu 10.1.99.10:8080
   SwitchServerFarm (VLAN 90)
        │
   DHCP-Server 72 = NetOps-Server 10.1.90.10   (DHCP + DNS + NetOps bot, task SYSTEM "NetOps-Bot")
```

| Vì sao node 72 | |
|---|---|
| Không sửa firewall | Server Farm đã được ra 443 và tới 10/8 |
| Không phá quy tắc thiết kế | VLAN 99 vẫn không ra Internet |
| Tách khỏi thứ đang giám sát | Ryu/OVS chết thì bot vẫn báo được |
| Không thêm phụ thuộc | Ở đâu bot cũng cần DNS `10.1.90.10` |
| Tài nguyên | x64, 8 GB RAM, nâng 2 vCPU |

**Phạm vi giai đoạn A** (`NETOPS_TRANSPORT=ssh`; chỉ thiết bị có `mgmt_ip`):

| Thiết bị | IP quản trị | Ghi chú |
|---|---|---|
| Core-SW1 | 10.1.90.2 | |
| Core-SW2 | 10.1.90.3 | Vlan99 của Core-SW2 `shutdown` có chủ đích |
| SwitchServerFarm | 10.1.99.32 | thêm `ip default-gateway 10.1.99.1` (trước đó không trả lời được subnet khác) |
| Ryu | 10.1.99.10:8080 | REST, chỉ dùng GET |
| SwitchDMZ | — | **ngoài phạm vi**: chỉ nối cổng DMZ của FW (VLAN 101), không có VLAN 99 về Core; quản trị ngoài băng (console) để không phải mở lỗ FW vào DMZ |
| vEdge, chi nhánh, SP | — | giai đoạn B (qua overlay SD-WAN) |

**Cấu hình đã áp trên 3 switch** (live 29/10/2026, `write memory`; `configs/` và config nhúng đã cập nhật, dòng `username` chỉ ghi chú vì repo không chứa bí mật):

```
ip domain-name campus.internal
ip ssh version 2
crypto key generate rsa modulus 2048
username netops privilege 15 secret <file credentials cục bộ>
ip access-list standard NETOPS_MGMT
 permit 10.1.90.10            ! NetOps-Server
 permit 10.1.99.50            ! PC-Management
 deny   any log
line vty 0 4
 access-class NETOPS_MGMT in
 login local
 transport input ssh
```

Đã kiểm live: SSH v2 bật trên cả 3 switch. SSH từ nguồn không có trong ACL (Core-SW1 `10.1.99.1` → SwitchServerFarm) bị `Connection refused`, và switch ghi log `%SEC-6-IPACCESSLOGNP: list NETOPS_MGMT denied 10.1.99.1`.

**Cài lên node 72:** `python scripts/build_windows_bundle.py` tạo `dist/netops/`, gồm:
- Python 3.11.9 embeddable, UCRT app-local (node 72 chưa có KB2999226) và thư viện `win_amd64`;
- code bot, `run.cmd`, `install.ps1`.

Chép thư mục này thành `C:\netops` lúc node tắt, đặt `secrets\credentials.md` (chỉ các dòng `netops` và `vManager (33)`), rồi chạy một lần:

```
powershell -ExecutionPolicy Bypass -File C:\netops\install.ps1
```

Script sẽ khoá `secrets\` và `.env` (chỉ SYSTEM/Administrators), chạy unit test, đăng ký task `NetOps-Bot` khởi động cùng máy dưới quyền SYSTEM, rồi chạy `selftest.py`. Selftest kiểm lần lượt DNS → HTTPS ra Internet qua FW → SSH từng thiết bị → Ryu → vManage.

### Kết quả triển khai thật trên node 72 (29/10/2026)

- **Môi trường chạy**: Python 3.11.9 chạy được trên Windows Server 2012 R2 (6.3.9600) nhờ UCRT app-local; 52 unit test đạt; task `NetOps-Bot` (SYSTEM, ONSTART) đã đăng ký.
- **`selftest.py`: 9/9 đạt.**
  - DNS phân giải `api.telegram.org` và máy chủ LLM (`openrouter.ai`).
  - HTTPS qua FW: Telegram HTTP 200; LLM gọi thật 1 lượt (HTTP 200 = key + model dùng được).
  - SSH in-band tới Core-SW1, Core-SW2, SwitchServerFarm.
  - Ryu: 6/6 OVS, 13/13 link.
  - vManage `https://10.9.0.10`: 11/12 reachable, đi theo đường Internet của lab.
- **Chạy in-band từ node 72**:
  - `/diag dhcp 100`: mọi lớp bình thường (relay 4 SVI, ping DHCP-Server 5/5).
  - `/diag sdn`: khựng 7 lần/giờ, lâu nhất 0,8 s.
  - `/compliance 100`: Core-SW1 và Core-SW2 đều 8/8.
  - `/backup 100`: 3/3 thiết bị.
  - `/change` `shutdown` Ethernet2/1 trên SwitchServerFarm → kiểm sau thay đổi phát hiện mất cổng → **tự rollback bằng `configure replace`**.
  - `/change` description → `done` → **hoàn tác** `undone`.

Ba lỗi mạng **có sẵn từ trước** được tìm ra trong lúc triển khai. Hai lỗi đầu đã sửa bằng chính quy trình `/change` (có điểm khôi phục, có kiểm sau thay đổi):

| Lỗi | Bằng chứng | Sửa |
|---|---|---|
| Site 100 không ra Internet: ASA **không ECMP giữa hai interface**, nên chiều về các VLAN chọn `inside2` (Core-SW2) trong khi phiên ra đi `inside` (Core-SW1, master VRRP) | Bắt gói: SYN-ACK về tới outside của FW rồi mất; capture `asp-drop`: `(no-adjacency) No valid adjacency` | Core-SW2 `ip ospf cost 10` trên Vlan10/20/30/40/90, để chiều về đi theo master VRRP; Core-SW2 vẫn là đường dự phòng (#0fc718) |
| SwitchServerFarm bật `ip routing` nên `ip default-gateway` bị bỏ qua, không trả lời được subnet khác | `Gateway of last resort is not set`; ACL đếm permit tăng nhưng ping 0/2 | `ip route 0.0.0.0 0.0.0.0 10.1.99.1` (#8dc38d) |
| Card mạng node 72 dùng DNS `10.1.90.1` (VIP VRRP, không phải DNS server) | `ipconfig /all` | Đặt DNS `127.0.0.1` (máy chủ DNS tự phân giải) |

Lưu ý vận hành trên Windows Server 2012 R2: console `cmd` lỗi khi Python in UTF-8 dưới `chcp 65001` (`PermissionError ... device not functioning`). Nên ghi kết quả ra file (`logs\selftest.txt`); bản thân bot chạy dưới Task Scheduler không bị ảnh hưởng.

Để bot hoạt động trên Telegram: điền `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS`, `API_KEY` vào `C:\netops\app\.env`. Bot chỉ đọc `.env` lúc khởi động. Khi chưa có token, bot thoát ngay và `run.cmd` chạy lại sau 30 s, nên tự nhận token mới. Nếu bot **đang chạy** mà sửa `.env` (vd thêm `chat_id`), phải dừng tiến trình để `run.cmd` khởi động lại:
`powershell -c "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | ? { $_.CommandLine -like '*telegram_bot*' } | % { Stop-Process -Id $_.ProcessId -Force }"`.

Ghi chú khi điền `.env` trên Server 2012 R2: Notepad đời này không hiểu xuống dòng kiểu Linux (cả file dồn thành một dòng), nên file `.env` phải dùng xuống dòng CRLF. Trình duyệt trên node quá cũ để mở Telegram Web/trang quản lý key LLM, nên lấy token trên điện thoại hoặc laptop.

Chế độ console EVE (mặc định khi không đặt `NETOPS_TRANSPORT`) giữ lại làm **công cụ ngoài băng của người quản trị lab**, giống console server. NetOps-Server không dùng chế độ này.

## Luồng chạy và đường vào lab (chế độ console — công cụ quản trị lab)

```
 Điện thoại ──HTTPS──► api.telegram.org ◄──long polling (bot tự gọi ra, không mở cổng vào)──┐
                                                                                          │
                                                    Máy chạy bot (laptop / VM EVE) ───────┘
                                                    telegram_bot.py
                                                     ├─ kiểm chat_id / người duyệt
                                                     ├─ lệnh /… → campus.service (không qua LLM)
                                                     └─ câu hỏi tự nhiên → LangGraph ──HTTPS──► LLM API (OpenRouter)
                                                           (chỉ thấy câu hỏi + output đã che bí mật, KHÔNG thấy mật khẩu)
                                                     │
                                                     │ SSH :22 (root, mật khẩu từ file credentials cục bộ)
                                                     │ qua Tailscale 100.86.110.39 hoặc LAN 10.215.26.50
                                                     ▼
                                     Server EVE-NG (SDWAN_LAB) — một kết nối SSH, nhiều kênh direct-tcpip
             ┌───────────────────────────────┼───────────────────────────────────┐
             ▼                               ▼                                   ▼
  127.0.0.1:32768+node-id         10.9.1.10:443 (vManage)              <ens6 node 9>:8080 (Ryu)
  console telnet của từng node    route 10.9.1.0/24 qua Switch61       qua pnet0 (Cloud-NAT)
  (IOL/vIOS/ASA/vEdge)            e0/0 → Vlan10 10.9.1.1               /campus/health, /stats/flow
  = out-of-band, không đi qua     REST dataservice: device, alarms
  mạng dữ liệu của lab
```

- Bot vào thiết bị **out-of-band** qua console EVE, giống console server trong doanh nghiệp. Nhờ vậy không cần bật SSH hay IP quản trị trên thiết bị, và vẫn vào được khi VLAN 99, routing hay firewall trong lab đang hỏng (lúc cần chẩn đoán nhất).
- REST (vManage, Ryu) đi cùng kết nối SSH đó: `campus/tunnel.py` mở cổng `127.0.0.1:<ngẫu nhiên>` trên máy bot rồi chuyển tiếp qua server EVE.
- Telegram không bao giờ kết nối vào máy bot. Bot chủ động hỏi Telegram (long polling), nên máy bot chỉ cần đi ra Internet.
- Mỗi node chỉ có một phiên console tại một thời điểm (có khoá theo node). Bot không gõ đè khi console đang ở config mode.

## Cài đặt

```bash
cd tools/campus-netops-bot
python -m venv .venv && .venv\Scripts\activate      # Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                              # rồi điền API_KEY, TELEGRAM_*, EVE_HOST
```

File credentials (`CAMPUS_CRED_FILE`) là bảng Markdown `| thiết bị | tài khoản | mật khẩu | ghi chú |`. Khoá tra cứu là chuỗi con của cột đầu: `EVE-NG SDWAN_LAB`, `FW-ASAv 1, 2`, `vEdge Site 100`, `vEdge chi nhánh`, `vManager (33)`, `vSmart (34)`, `vBond (35)`.

## Chạy

```bash
python -m unittest discover -s tests -v                          # kiểm thử offline (48 test)
python scripts/smoke_console.py vEdge1-S300 "show bfd sessions"  # thử live một lệnh, không cần LLM
python main.py                                                   # chat trên terminal
python telegram_bot.py                                           # Telegram ChatOps
npx @modelcontextprotocol/inspector python mcp_cisco_server.py   # MCP Inspector
python scripts/export_netbox.py                                  # CSV import NetBox (không có mật khẩu)
```

Lệnh Telegram: `/devices 300`, `/show Core-SW1 show vrrp brief`, `/ping vEdge1-S300 100.64.30.2 0`, `/diag vEdge2-S200`, `/diag dhcp 300`, `/diag sdn`, `/alarms 24`, `/health`, `/sdn`, `/flows Dist-SW1`, `/change`, `/changes`, `/undo`, `/compliance`, `/backup`, `/drift`. Lần đầu nhắn `/start`, bot sẽ trả về `chat_id` để bạn điền vào `.env`.

Bot cần đi tới server EVE (`EVE_HOST`): IP Tailscale `100.86.110.39` hoặc LAN `10.215.26.50`. Muốn chạy 24/7 thì đặt bot trên chính VM EVE, hoặc một máy trong tailnet có Internet để gọi Telegram/LLM.

## Lộ trình

- ~~GĐ2~~: đã xong (xem trên). Riêng OVS/Ryu hiện chỉ đọc (health, flow).
- ~~GĐ3~~: đã xong (xem trên).
- Tiếp theo (tuỳ chọn): rollback cho ASA (dùng `copy running-config` + `configure replace` của ASA 9.x hoặc lệnh ngược), `/test failover` gọi `sdwan_reliability.py`, lưu yêu cầu thay đổi ra file để không mất khi bot khởi động lại, user SSH riêng trên server EVE chỉ cho `direct-tcpip` thay vì `root`.

## Tác giả

**Trần Hữu Nhân**, nhóm đồ án Campus Network SDN + SD-WAN (cùng Nguyễn Nhật Hào).
