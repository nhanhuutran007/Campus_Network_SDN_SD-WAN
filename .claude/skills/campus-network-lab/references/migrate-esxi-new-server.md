# Chuyển lab sang server ESXi mới + truy cập bằng Tailscale

Kế hoạch người dùng chốt hướng ngày **25/10/2026**. **Chỉ bắt đầu khi (1) người dùng nhắn chốt VÀ (2) người quản lý server đồng ý cho tạo VM.** Đây là server dùng chung của người khác; mọi bước tạo/bật VM, xin IP đều phải được phép trước (xem Rào an toàn trong SKILL.md).

Nguyên tắc minh bạch: Tailscale và mọi đường truy cập đặt **trong VM EVE của mình**, công khai với quản lý nếu được hỏi — **không** tạo đường ẩn, cửa hậu, hay lách quyền kiểm soát trên hạ tầng của họ. Lý do dựng Tailscale chỉ là để có đường truy cập dự phòng ổn định (không phụ thuộc VPN chung mà quản lý có thể tắt), không phải để che giấu.

## Mục lục
- Hạ tầng đích (đã khảo sát 25/10)
- Điều kiện tiên quyết (người dùng lo)
- Bước 1: Tạo VM trên ESXi
- Bước 2: Cài EVE-NG
- Bước 3: Tailscale trong VM (minh bạch)
- Bước 4: Chép lab từ host 1
- Bước 5: Bật thử + nghiệm thu
- Rủi ro và lưu ý

## Hạ tầng đích (đã khảo sát 25/10/2026, chỉ đọc qua vSphere API)

- **ESXi mới `10.215.26.20`**: VMware ESXi 8.0.3, **license Enterprise Plus** (API tạo/bật VM được — bản free chỉ cho đọc). Dell R650xs, 2× Xeon Gold 6338 (64 core/128 thread, 2,0 GHz), 511 GB RAM, **datastore SSD** `26.20` (3,4 TB, trống ~2,1 TB), nested HV = True. Không bị vCenter quản lý (kết nối trực tiếp host).
- **Portgroup có sẵn**: `VLAN 28` (cùng dải 10.215.28.x với host 1), `VLAN 26`, `Management Network`. → card WAN của VM nối `VLAN 28` để chung mạng/host 1.
- **ISO có sẵn trên datastore** (không cần upload): `eve-ce-prod-6.2.0-4-full.iso`, `ubuntu-24.04.3-live-server-amd64.iso`, `cml2_2.10.1-21...`, `refplat-...`, `windown 7...`, `ise-3.2...`.
- **VM người khác đang bật** (KHÔNG đụng): EVE-NG TRI_NVP (128 vCPU/256 GB), CML 2.10.1 (128/128), vCenter (8/32), Solawin (8/64). RAM host dùng ~186/511 GB, CPU ~5% lúc khảo sát.
- Mật khẩu root ESXi: đọc `~/.claude/campus-lab-credentials.md` mục "ESXi ứng viên 10.215.26.20". So sánh với máy chạy host 1 ở [[project-candidate-esxi-2026-10-25]].
- Công cụ đọc/điều khiển: `pyvmomi` (đã `pip install --user`); script khảo sát ở scratchpad phiên 25/10 (`esxi_info.py`, `esxi_vmstats.py` — có thể mất, viết lại từ mô tả này).

## Điều kiện tiên quyết (người dùng lo)

1. **Quyền**: quản lý đồng ý tạo 1 VM cho đồ án. Chỉ quản lý/tạo đúng VM của mình.
2. **IP tĩnh**: xin 1 IP trống trong `VLAN 28` (hoặc 26.x) từ người quản lý mạng, tránh trùng. Không tự chọn bừa.
3. **Cấp phát tài nguyên — DÙNG CHUNG, KHÔNG reservation** (người dùng chốt 25/10): làm giống VM TRI_NVP đang chạy (res CPU 0, res RAM 0 — cấp phát lười, nhường tài nguyên cho host). KHÔNG đặt memory/CPU reservation.
4. **Kích thước VM**: đề xuất ~32–48 vCPU / 192 GB RAM, đĩa thin ~1 TB trên SSD. Cân nhắc đừng cấp quá nhiều vCPU (VM nhiều vCPU dễ bị CPU ready cao khi host bận). `.unl` khai báo ~58 vCPU/142 GB nhưng host 1 thực dùng ~45 GB nhờ cấp phát lười → 192 GB là dư thoải mái. Chốt số cuối với người dùng trước khi tạo.

## Bước 1: Tạo VM trên ESXi

- Tạo qua pyvmomi (`CreateVM_Task`) hoặc govc. Guest OS: `ubuntu64Guest` (EVE CE 6.2 nền Ubuntu 20.04 focal — KHÔNG để nền 22.04/24.04).
- **Bật nested virtualization**: `vhv.enable = TRUE` (hoặc `nestedHVEnabled=True` trong config spec) — bắt buộc để node trong EVE chạy KVM. Expose hardware-assisted virt tới guest.
- CPU/RAM theo mục trên, **không reservation**. Firmware: BIOS (EVE 6.2 quen BIOS; nếu EFI thì chỉnh boot). SCSI: pvscsi; đĩa thin provision trên datastore `26.20`.
- NIC: VMXNET3 nối portgroup `VLAN 28`. (EVE dùng NIC đầu làm management `pnet0`.)
- Gắn ISO `eve-ce-prod-6.2.0-4-full.iso` từ datastore vào CD, boot từ CD.

## Bước 2: Cài EVE-NG

- Bật VM, điều khiển cài đặt qua console: gửi phím + chụp màn hình bằng API (`AcquireMksTicket`/screenshot, hoặc webMKS) để theo dõi — không cần người dùng bấm. (Cách gõ phím/chụp giống thao tác VNC node Windows: gõ chậm, chụp để xác nhận.)
- Cài EVE **CE** (không Pro). Đặt: IP tĩnh (bước tiên quyết), hostname, DNS, NTP, mật khẩu root.
- Sau cài: bật SSH, `apt` cập nhật tối thiểu nếu cần, kiểm `/dev/kvm` tồn tại + `egrep -c '(vmx|svm)' /proc/cpuinfo` > 0 (nested OK). Ghi mật khẩu root EVE mới vào file credentials.
- Firewall: chỉ mở 22/443 cho IP người dùng + dải Tailscale (mật khẩu lab đã lộ trên git — xem Rào an toàn).

## Bước 3: Tailscale trong VM (đường truy cập riêng, minh bạch)

**Trạng thái 25/10/2026: ĐÃ XONG.** Cài trong VM (không cài lên ESXi), `tailscale up --hostname=eve-sdwan-lab --accept-dns=false` và người dùng tự đăng nhập bằng link (không cần auth key) → `100.86.110.39`. Chưa bật subnet router. Thêm người khác (Hào): dùng **Share** máy `eve-sdwan-lab` trong admin console (người nhận dùng tài khoản riêng, chỉ thấy VM này). Nhớ **Disable key expiry** cho VM.

### Khái niệm (vì sao độc lập với VPN chung)

- Tailscale **không** phải VPN tập trung kiểu nhiều người chui vào một cổng. Nó là mạng riêng (tailnet) gắn với **tài khoản Tailscale của người dùng**. Mỗi máy (laptop người dùng, VM EVE) **tự gọi RA Internet** tới máy điều phối Tailscale, rồi bắt tay **trực tiếp (peer-to-peer)** với nhau (WireGuard, mã hoá đầu-cuối). Khi đã vào tailnet, người dùng gõ thẳng IP Tailscale `100.x.x.x` của VM là tới — **không cần bật VPN dùng chung**. VPN chung bị quản lý tắt/xoá cũng không ảnh hưởng đường này.
- Đây là "đường của riêng mình": chỉ máy nào người dùng cho vào tailnet mới thấy nhau; IP lab/mạng đổi vẫn vào được bằng IP `100.x.x.x` cố định; chui qua NAT mà không cần mở cổng vào.

### Điều kiện để độc lập THẬT (phải kiểm lúc build)

- Tailscale độc lập với VPN chung **chỉ khi VM EVE có đường RA Internet riêng, không đi qua chính VPN chung đó**. VM cần ra được **TCP 443** và tốt nhất **UDP 41641** (NAT traversal; nếu UDP bị chặn, Tailscale vẫn chạy nhưng relay qua DERP, chậm hơn).
- Dấu hiệu tốt: node 9 trên host 1 ra Internet được qua Cloud-NAT (REST controller có IP `10.215.28.x`). **Kiểm lúc build**: từ VM EVE `curl -I https://login.tailscale.com` và `tailscale netcheck` (xem UDP/DERP).
- VPN chung mà người dùng đang dùng là đường **từ ngoài chui vào** mạng nội bộ 10.215.x.x; Tailscale thay đúng việc đó bằng cách cho VM và laptop gặp nhau qua Internet thường.

### Hai mức truy cập

1. **Vào thẳng VM EVE** (SSH, GUI web EVE :443, Console): chỉ cần Tailscale trên VM; dùng IP `100.x.x.x`.
2. **Tới node/host 1 bên trong** (10.215.28.x, 10.1.x, 10.2.x…): bật **subnet router** trên VM — `tailscale up --advertise-routes=10.215.28.0/24` + bật IP forwarding (`net.ipv4.ip_forward=1`), duyệt route trong admin console Tailscale, phía laptop `--accept-routes`. Laptop đi qua VM như một cửa vào mạng lab.

### Các bước

- Người dùng **tự** tạo tài khoản Tailscale và sinh **auth key** (không đưa Claude tạo tài khoản/đăng nhập giúp). Dán key lúc chạy, **không commit/log/ghi vào repo**; nếu cần lưu thì để ở file credentials cục bộ.
- Cài trong VM EVE: `curl -fsSL https://tailscale.com/install.sh | sh` → `tailscale up --auth-key=... [--advertise-routes=10.215.28.0/24] --ssh` (`--ssh` nếu muốn Tailscale SSH thay cổng 22).
- Siết: firewall VM chỉ mở 22/443 cho IP người dùng + dải tailnet `100.64.0.0/10`; có thể dùng Tailscale ACL để chỉ thiết bị của người dùng vào được.
- Bền bỉ: đặt auth key dạng không hết hạn hoặc gia hạn; `tailscaled` chạy như service tự bật khi VM reboot → mất điện/khởi động lại vẫn tự lên.

### Minh bạch và phạm vi

- Đường này **của riêng người dùng** nhưng **không giấu**: chạy trên VM được cấp, nếu quản lý hỏi thì trả lời được. Mục đích là truy cập dự phòng ổn định khi VPN chung bị tắt — không phải cửa hậu.
- **Không** tạo đường ẩn/lách quyền kiểm soát trên hạ tầng của quản lý. Chỉ cài phần mềm trong **VM của mình**; không cài gì lên ESXi host hay VM người khác.
- Thành thật về giới hạn: Tailscale độc lập với VPN chung nhưng không miễn nhiễm — quản lý làm chủ cả mạng nên vẫn có thể chặn Tailscale ở tường lửa hoặc cắt Internet mạng lab. Vì vậy vẫn giữ sao lưu (host 2, bản exact) để không mất dữ liệu khi mất truy cập.

## Bước 4: Chép lab từ host 1

- Dùng lại quy trình/script **host2-sync** ([[host2-sync.md]], `scripts/host2-sync/`). Khác biệt lợi thế: server mới SSH trực tiếp tới host 1 (10.215.28.26) được → chép **thẳng server↔server**, không relay qua laptop (nhanh hơn nhiều so với host 2).
- Nguồn đầy đủ & nhất quán: bản exact trên host 2 `/root/h1-backup-20261019/` (`.unl` md5 `744a7d6c…`, CA SD-WAN, nvram/vlan.dat) hoặc chép trực tiếp host 1 khi **node đã tắt** (copy overlay node đang chạy = đĩa hỏng).
- Base image phải **md5 giống hệt** trước khi gắn overlay (sự cố 13/10). 4 image tự cài + vtedge/vtsmart/vtbond/vtmgmt 20.10.1 + ASAv 9.20.2.2 + IOL(+`iourc`) + vIOS.
- Tenant trên server mới ≠ 6 → console port đổi (`32768 + 128*tenant + id`); IOL device-id = `(node_id & 0x3f)<<4 | tenant` → kiểm node 64 (xem host2-sync: có thể phải đổi id như bản host 2, dùng `fix64.py`); dùng **`lab-h1-exact.unl`** nếu giữ nguyên id. Áp bản vá `.lock` (`CAMPUS-PATCH` trong `cli.php`).
- md5 hai đầu mọi file. Không mở/save lab bằng GUI EVE.

## Bước 5: Bật thử + nghiệm thu

- Bật theo nhóm như đợt khôi phục 13/10: dịch vụ nền (3,4,24,72) → controller 9 → Dist 5,8 → Access 66/68/69/70 → VPC; rồi SD-WAN (34,35, vManage 33, vEdge) → chi nhánh.
- Kiểm: Ryu 6/6 OVS (`curl localhost:8080/stats/switches`), VPC nhận DHCP; vEdge control connections/OMP/BFD; vManage GUI.
- **Kỳ vọng hết khựng**: server mới CPU đời mới + SSD + còn rảnh → đo lại CPU ready/costop của VM khi lab chạy (`esxi_vmstats.py`) để xác nhận, và đo lại stall count của Ryu. Nếu vẫn khựng do VM khác giành CPU → báo người dùng cân nhắc (vì đã chọn không reservation).

## Rủi ro và lưu ý

- Server **dùng chung, không reservation**: nếu TRI_NVP/CML chạy lab nặng cùng lúc, lab mình vẫn có thể bị tranh CPU/RAM (giống host 1). Đây là đánh đổi người dùng chấp nhận để không chiếm RAM cố định.
- Không reservation + host RAM có thể đầy → ESXi có thể balloon/swap VM mình → chậm đĩa. Theo dõi `balloonedMemory`/`swappedMemory`.
- Mật khẩu root ESXi của cả 2 server do người dùng gửi qua chat → nhắc người dùng đổi nếu server không phải của họ.
- Mọi rào an toàn của skill vẫn áp dụng: không wipe node `config="0"`, không stopall, không đẩy mật khẩu lên repo, hỏi trước khi tắt/bật/ghi.
- Giữ host 1 nguyên vẹn cho tới khi server mới nghiệm thu xong (đồng bộ một chiều, host 1 là nguồn chuẩn).
