# Cho người dùng các site ra Internet (DIA) — kế hoạch và tiến độ

Người dùng đồng ý hướng này ngày 28/09/2026. Làm theo giai đoạn, mỗi giai đoạn kiểm thử xong mới sang giai đoạn sau. Host 1 trước, rồi repo, rồi host 2.

## Kiến trúc chốt

- **Direct Internet Access tại từng site + dự phòng qua Site 100**: PC → Brand-FW (chi nhánh) / FW-ASAv (S100) → vEdge có màu `biz-internet` NAT → Router Internet PAT → LAN thật → Internet.
- vEdge1 chi nhánh (chỉ MPLS) chuyển default sang vEdge2 cùng site qua link VPN 1 (`10.x.2.0/30`). Mất biz-internet ở chi nhánh → default từ Site 100 qua OMP (độ ưu tiên thấp).
- NAT hai tầng: vEdge → IP WAN `203.0.113.x`; Router Internet → IP LAN thật (giống nhà mạng CGNAT). `203.0.113.0/24` (tài liệu) và `100.64.0.0/10` (CGNAT) không đi được trên Internet thật.
- Split DNS: client vẫn dùng `10.1.90.10`; DNS 72 forward `8.8.8.8`/`1.1.1.1`, tắt root hints; ACL `INSIDE_OUT` chỉ cho DNS server hỏi ra ngoài.
- VLAN 99 (quản trị) và Site 900 không ra Internet; chỉ chiều đi ra, không port-forward.
- Giới hạn chấp nhận: ASAv Unlicensed = 100 conn, ~100 Kbps (đủ ping/demo, không đủ lướt web).

## Giai đoạn 0 — kết quả (28/09/2026, host 1, chỉ đọc)

- Host 1: `pnet0` 10.215.28.26/24, gateway LAN **10.215.28.1**, host ra Internet OK (ping 8.8.8.8 ~46 ms).
- Router Internet (26): Gi0/0 **IP tĩnh 10.215.28.23/24** (NVRAM; repo ghi `dhcp`), MAC `5006.001a.0000`; ping 10.215.28.1 OK. **Không có route mặc định** ("Gateway of last resort is not set"), **không có NAT** ⇒ ping 8.8.8.8 từ router 0/3. BGP 6/6 Established; vẫn `default-originate` xuống vEdge.
- vEdge: VPN 0 có default (BGP + static) ✓; **VPN 1 không có default** ✓ (điểm chặn). vEdge2-S200 ge0/0 `203.0.113.9/30` biz-internet, chưa `nat`.
- **Phát hiện cần xử lý ở giai đoạn 2**: vEdge1-S100 VPN 0 có **2 default ECMP** (MPLS `100.64.100.2` + Internet `203.0.113.2`). MPLS không có Internet ⇒ DIA phải chỉ đi cổng có `nat` (ge0/3 biz-internet); kiểm lại sau khi bật, nếu lưu lượng lệch sang MPLS thì bỏ/giảm ưu tiên default MPLS cho DIA.
- `inspect icmp` đã có trên FW-ASAv S100 và Brand-FW; FW-ASAv đã có default về vEdge + `default-information originate`.
- Cần xác nhận với người dùng: `10.215.28.23` nằm ngoài dải DHCP của router LAN (tránh trùng IP).

## Giai đoạn 1 — ĐÃ XONG (28/09/2026, host 1)

- Router Internet Gi0/0: bỏ IP tĩnh `.23`, chuyển **`ip address dhcp`** (người dùng yêu cầu, tránh trùng IP LAN) → nhận `10.215.28.69`, route mặc định qua `10.215.28.1` do DHCP cài (AD 254) — không cần route tĩnh. `ip nat outside` Gi0/0, `ip nat inside` Gi0/1–0/7, ACL `NAT_ISP` (203.0.113.0/24, 100.64.0.0/10), `ip nat inside source list NAT_ISP interface Gi0/0 overload`. Site 900 `10.9.x` cố ý không NAT.
- Kiểm chứng: router ping 8.8.8.8 5/5 (~48 ms); nguồn 203.0.113.10 và 100.64.254.1 đều 5/5; `show ip nat translations` thấy PAT → 10.215.28.69; vEdge2-S200 `ping vpn 0 source ge0/0 8.8.8.8` 3/3; BGP 6/6 không reset; BFD vEdge2-S200 8/8.
- Bẫy: `write memory` gửi chung chuỗi lệnh đã không lưu (startup vẫn bản 20/08 — IP tĩnh `.23` trước đó cũng chưa từng được lưu). Gửi riêng `write memory`, chờ `[OK]` + GRUB ghi xong, rồi đọc lại `show startup-config` (vIOS đọc chậm, cần chờ lâu).
- Repo `configs/06-ServiceProvider/Internet/config.cfg` đã cập nhật; config nhúng trong `.unl` (node 26) chưa embed lại.

## Giai đoạn 2 — ĐÃ XONG (28/09/2026, host 1, Site 100)

- vEdge1-S100: `vpn 1 ip route 0.0.0.0/0 vpn 0` + `vpn 0 interface ge0/3 nat`; vEdge2-S100: tương tự với `ge0/2`. Route VPN 1 hiện kiểu **`nat`** chỉ qua cổng biz-internet (không dùng MPLS dù VPN 0 có 2 default ECMP).
- **Sự cố và sửa (quan trọng):**
  1. Commit trên vEdge làm phiên BGP vEdge S100 ↔ Internet mới lên lại ⇒ vEdge **quảng bá ngược default học từ MPLS** (AS-path `65000 64512`) lên router Internet; eBGP AD 20 thắng DHCP default AD 254 ⇒ router Internet mất Internet (vòng lặp). Sửa chuẩn ISP: `ip prefix-list NO_DEFAULT_IN` (deny 0/0, permit le 32) áp **in** cho 5 vEdge + MPLS trên router Internet, `clear ip bgp * soft in` (không reset phiên).
  2. VPN 0 của vEdge chia tải default qua MPLS; MPLS không có đường ra Internet ⇒ thêm `neighbor 100.64.254.2 default-originate` trên router Internet (MPLS nhận default từ nhà mạng Internet — mô hình MPLS có Internet tập trung). Cổng Gi0/1 đã `nat inside`, ACL gồm 100.64/10.
- Kiểm chứng: vEdge1/2-S100 `ping vpn 1 source ge0/0 8.8.8.8` 3/3; vEdge2 VPN 0 3/3; **Core-SW1 nguồn VLAN10 và VLAN40 5/5 (~82 ms)** qua FW-ASAv; router Internet default lại `S* via 10.215.28.1`, BGP 6/6 không reset; vEdge1-S200 BFD 8/8, OMP up.
- Route DIA kiểu `nat` **không** được quảng bá qua OMP (chi nhánh chưa có default) ⇒ dự phòng qua Site 100 phải cấu hình tường minh ở giai đoạn 3.
- Bẫy console: vIOS console tự rơi về user mode `>` sau thời gian chờ — luôn `enable` trước khi cấu hình; gõ `end` ở `>` bị hiểu là tên máy (tra DNS).
- Repo đã cập nhật: vEdge1/2-S100, Internet (prefix-list, default-originate MPLS).

## Giai đoạn 3 — chi nhánh (28/09/2026): S300 XONG, S200 dở, S400 chưa

**Thiết kế chi nhánh đã điều chỉnh (thay cho "vEdge1 default → vEdge2"):** tường lửa chọn đường ra.
- Brand-FW: `route outside2 0.0.0.0 0.0.0.0 <IP vEdge2> 1` (Internet đi vEdge2 có biz-internet); `route outside1 10.0.0.0 255.0.0.0 <IP vEdge1> 1 track 1` + `route outside2 10.0.0.0 255.0.0.0 <IP vEdge2> 2` (overlay nội bộ giữ như cũ); giữ `route outside1 10.1.255.1/32 …` cho SLA. Thứ tự áp: thêm 10/8 trước, xoá 2 default cũ, thêm default mới, `write memory`.
- vEdge2 (biz-internet): `vpn 1 ip route 0.0.0.0/0 vpn 0` + `vpn 0 interface ge0/0 nat`.
- vEdge1 (MPLS): **KHÔNG** đặt default tĩnh — `omp advertise static` làm nó **rò vào OMP** sang mọi site (đã gặp: vEdge2-S300 thấy default OMP từ 10.200.200.1). Default DIA kiểu `nat` thì không lên OMP.
- vEdge2 không NAT được lưu lượng đi vòng vEdge1→vEdge2 (Brand-FW ping qua outside1 0/5, bảng `show ip nat filter` không có luồng VPN 1) — lý do thêm để chọn thiết kế trên.

**S300 (xong, kiểm chứng):** vEdge2-S300 DIA; Brand-FW-S300 route mới, `write memory` [OK]; Brand-FW → 8.8.8.8 5/5, 1.1.1.1 5/5; overlay → 10.2.1.2 và 10.4.1.2 đều 5/5; PC-TaiChinh-S300 lease 10.3.90.100.
**S200:** vEdge2-S200 DIA đã cấu hình (VPN 1 → 8.8.8.8 3/3); vEdge1-S200 đã gỡ default rò; **còn** đổi route Brand-FW-S200 (node 37 đang tắt).
**S400:** chưa làm (LAN tắt): vEdge2-S400 (41) ge0/0 DIA + Brand-FW-S400 (38): Internet → vEdge2 `10.4.1.6` (outside2), 10/8 → vEdge1 `10.4.1.2` (outside1, track 1).
**Chưa làm:** dự phòng Internet qua Site 100 khi mất biz-internet chi nhánh (cần cách quảng bá default có kiểm soát — không dùng static trên vEdge1).
**Vấn đề riêng phát hiện:** track SLA Brand-FW-S300 tới 10.1.255.1 đã đổi trạng thái 126 lần (vEdge1/2-S100 dùng chung loopback 10.1.255.1) — cần xem xét riêng.
**Lưu ý DNS:** client chi nhánh nhận DNS 10.1.90.10 (Site 100) — khi DHCP-Server 72 tắt, chỉ ping theo IP được; tên miền cần giai đoạn 4.

## Các giai đoạn tiếp

1. Router Internet: `ip nat inside` Gi0/1–0/7, `ip nat outside` Gi0/0, ACL `203.0.113.0/24` + `100.64.0.0/10`, `overload` ra Gi0/0; `ip route 0.0.0.0 0.0.0.0 10.215.28.1` (host 2: theo LAN của host 2). Kiểm `ping 8.8.8.8 source Gi0/5`.
2. Site 100: vEdge1/2-S100 `vpn 1 ip route 0.0.0.0/0 vpn 0`; `nat` trên cổng biz-internet (vEdge1 ge0/3, vEdge2 ge0/2).
3. Chi nhánh (S200 trước): vEdge2 như trên; vEdge1 `vpn 1` default → vEdge2 (`10.x.2.2`); dự phòng qua OMP từ S100.
4. DNS forwarder + sửa `INSIDE_OUT`.
5. Chính sách (VLAN 99/Site 900 chặn; Server/DMZ chỉ HTTP/HTTPS/NTP; log Syslog).
6. Ma trận kiểm thử (ping/nslookup mỗi site, traceroute, cắt biz-internet S200, VLAN 99 bị chặn, tên nội bộ vẫn đúng).
7. Cập nhật `configs/`, tài liệu, skill; đồng bộ host 2.
