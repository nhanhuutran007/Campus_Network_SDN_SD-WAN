# Phương án khi mất host 1: dựng lại lab trên Google Cloud

Kế hoạch người dùng chốt ngày **19/10/2026**. **Chỉ triển khai khi người dùng yêu cầu rõ** — đây là kế hoạch, chưa có tài nguyên cloud nào được tạo. Giá/điều khoản dưới đây tra web ngày 19/10/2026 (phần lớn từ trang thống kê bên thứ ba) → kiểm lại bằng Google Pricing Calculator trước khi chốt.

## Mục lục
- Bối cảnh và lựa chọn
- Nguồn dữ liệu để dựng lại
- Máy cloud và giới hạn
- Ngân sách 300 USD / 90 ngày
- Các bước triển khai
- Rủi ro và lưu ý

## Bối cảnh và lựa chọn

- Laptop người dùng chỉ có **16 GB RAM** → không chạy nổi cả lab. Host 2 (PC boot USB) 8 GB → chỉ chạy từng nhóm.
- `.unl` khai báo **58 vCPU / 142 GB RAM** (vManage 33 = 4 vCPU / 32 GB); host 1 thực dùng ~45 GB nhờ cấp phát lười + KSM.
- PNETLab (fork EVE-NG) về nguyên tắc dùng được `.unl` + thư mục image cùng tên, nhưng **chọn EVE-NG CE** vì lab đang chạy trên EVE và EVE có hướng dẫn GCP chính thức (CE Book 6.2, mục GCP).
- Phương án dự phòng khi không có cloud: chạy theo kịch bản trên laptop (SDN / SD-WAN / chi nhánh, mỗi lần một nhóm node) và bỏ vManage (overlay + policy vẫn làm được bằng CLI vSmart).

## Nguồn dữ liệu để dựng lại

Repo chỉ có `.unl` + `configs/` (text) — **không có qcow2**. Chỉ 47 node `config="1"` tự nạp config nhúng; 23 node `config="0"` (OVS, Ryu 9, DHCP 72, Web/Mail/Syslog, PC, vManage/vSmart/vBond) chỉ có cấu hình **trong overlay**.

Thứ tự ưu tiên nguồn:
1. **Host 1** nếu còn truy cập được: chép thẳng host 1 → VM GCP (nhanh hơn relay qua laptop ~1,7 MB/s). Node phải **tắt** trước khi copy overlay; md5 hai đầu.
2. **Host 2**: bản sao host 1 ngày 19/10/2026 (`.unl`, overlay mọi node **kể cả đĩa vManage 33** — chỉ lưu, host 2 không đủ RAM chạy; nvram/vlan.dat IOL, CA SD-WAN ở `/root/h1-backup-20261019/`) — xem `host2-sync.md`. Base image cần **md5 giống hệt** (overlay gắn sai base → treo boot, như sự cố 13/10).
3. vManage 33: chép đĩa từ host 2 lên VM cloud (cần ~32 GB RAM khi chạy). Nếu đĩa hỏng: dựng vManage mới, dùng lại CA đã sao lưu, upload whitelist, làm lại template/policy; hoặc bỏ vManage.

Image cần có: 4 image tự cài (`linux-ubuntu-ovs-16p`, `linux-ubuntu-18.04-server`, `win-7-x86-IPCC-WSAlicensed`, `winserver-S2012-R2-x64`) + vtedge/vtsmart/vtbond/vtmgmt 20.10.1, ASAv 9.20.2.2, IOL + `iourc`, vios. Image tải từ kho PNETLab/Internet **khác md5** → không dùng được với overlay cũ.

## Máy cloud và giới hạn

- Tài khoản **dùng thử 300 USD / 90 ngày**; điều khoản giới hạn **8 vCPU chạy cùng lúc** → máy lớn nhất: **`n2-highmem-8` (8 vCPU, 64 GB)**. Muốn `n2-highmem-16` (128 GB, ~1,3 USD/h) phải nâng tài khoản trả phí (credit còn lại vẫn dùng).
- Region `asia-southeast1` (Singapore).
- Nested virtualization: dùng **N2 (Intel)**; **E2 và AMD (trừ N4D) không hỗ trợ**; chỉ KVM ở L1. Flag `--enable-nested-virtualization`, `--min-cpu-platform="Intel Haswell"` (hoặc mới hơn).
- OS: **Ubuntu 20.04** (EVE CE không chạy trên 22.04), cài `install-eve.sh` bản focal; cài gói CE, không cài Pro.
- 8 vCPU cho 58 vCPU khai báo → **bật theo đợt** (hạ tầng → controller → từng site), hoặc bỏ vManage.

## Ngân sách 300 USD / 90 ngày

| Khoản | Giá xấp xỉ |
|---|---|
| `n2-highmem-8` thường | ~0,65 USD/h |
| `n2-highmem-8` Spot | ~0,22–0,31 USD/h (chưa xác nhận credit dùng thử trả cho Spot) |
| pd-balanced 250 GB | ~27,5 USD/tháng → ~83 USD/3 tháng (tính cả khi tắt máy) |
| pd-standard 250 GB | ~11 USD/tháng (rẻ nhưng boot chậm) |
| IP công khai khi máy chạy | ~0,005 USD/h |

Phân bổ người dùng chọn (dư ~85 USD):
- Tuần 1 cài đặt + chép dữ liệu: Spot ~20 h (~5 USD).
- Làm lab hằng ngày: **Spot, 4–5 h/buổi**, tổng ~400 h (~105 USD).
- Demo, chụp ảnh báo cáo, ngày bảo vệ: **máy thường** ~30 h (~20 USD) — không dùng Spot khi demo.
- Đĩa 3 tháng ~83 USD.

Tham chiếu: chỉ máy thường → ~300 h ≈ 3,3 h/ngày; chỉ Spot → ~760 h ≈ 8,4 h/ngày.

## Các bước triển khai

1. Người dùng đăng ký GCP dùng thử (cần thẻ xác minh), tạo project, **Budget alert 100/200/250 USD**.
2. Tạo VM Ubuntu 20.04, `n2-highmem-8`, pd-balanced ~250 GB (chốt sau khi đo dung lượng image + overlay thật), nested virtualization, Spot với `--instance-termination-action=STOP`.
3. Cài EVE-NG CE (focal). Firewall chỉ mở 22/443 cho **IP người dùng** (mật khẩu lab đã lộ trên git).
4. Chép base image về đúng tên thư mục cũ → `fixpermissions`; chép `.unl` + thư mục config lab + overlay vào `/opt/unetlab/tmp/<tenant>/<lab-uuid>/<id>/` (tenant mới → console port = `32768 + 128*tenant + id`). md5 mọi file.
5. Bật thử từng nhóm như đợt khôi phục image 13/10 (OVS 68 → Windows 72/13/25/36/73 → Linux 22/18 → SD-WAN → chi nhánh), kiểm cấu hình còn nguyên; Ryu 6/6 OVS; vEdge OMP/BFD.
6. Script tự tắt VM sau ~5 h (`shutdown` hẹn giờ trong VM) + luôn `gcloud compute instances stop` khi xong.

## Rủi ro và lưu ý

- Spot bị thu hồi bất cứ lúc nào → node tắt đột ngột (giống stopall 12/10); lưu cấu hình thường xuyên.
- Hết 90 ngày/hết credit → tài nguyên dừng, dữ liệu bị xoá sau thời gian ân hạn (kiểm lại điều khoản) → tải về những gì cần giữ trước hạn.
- Các rào an toàn của skill vẫn áp dụng trên host cloud: không wipe node `config="0"`, không mở/save lab bằng GUI, không đẩy mật khẩu lên repo.

Nguồn: [GCP Free Trial terms](https://cloud.google.com/terms/trial) · [Nested virtualization](https://docs.cloud.google.com/compute/docs/instances/nested-virtualization/overview) · [Enable nested](https://docs.cloud.google.com/compute/docs/instances/nested-virtualization/enabling) · [Spot VMs](https://docs.cloud.google.com/compute/docs/instances/spot) · [Giá n2-highmem-8](https://gcloud-compute.com/n2-highmem-8.html) · [Giá đĩa](https://gcloud-compute.com/diskpricing.html) · [EVE CE Book 6.2](https://www.eve-ng.net/wp-content/uploads/2024/05/EVE-CE-BOOK-6.2-2024.pdf)
