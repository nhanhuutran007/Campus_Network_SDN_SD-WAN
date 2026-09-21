# Sản phẩm học thuật của đồ án: báo cáo, slide, tiến độ

Đồ án CNTT (học kỳ 3, năm 3): kết quả là **lab chạy được + tài liệu**. Mọi con số/khẳng định trong báo cáo và slide phải truy được về `.unl`, `configs/` hoặc một kết quả kiểm chứng thật.

## Các sản phẩm

| Sản phẩm | Vị trí | Ghi chú |
|---|---|---|
| Tài liệu thiết kế (nguồn sự thật cho báo cáo) | `campus_network_sdn_sdwan.md` | Mermaid topo 1.1–1.6, bảng IP 2.0–2.5, VLAN/DHCP 2.4, SDN 2.7 |
| Báo cáo LaTeX | `BAOCAO_DACNTT_LVT/` (`main.tex`, `content/Chapter1–5.tex`, `config/preamble.tex`, `tailieuthamkhao.bib`, `appendix.tex`) | `pdflatex` + `babel[vietnamese]` (MiKTeX); Chương 3 (mô hình đề xuất) lớn nhất, Chương 4 triển khai/kiểm thử/đánh giá, Chương 5 kết luận |
| Slide báo cáo tiến độ | `SlideTrinhBayDA/` (Beamer, `main.tex`, `Chapter/chapter1–5.tex`) | Chương 5 = "Kết luận báo cáo tiến độ" |
| Bảng theo dõi tiến độ | `BangTheoDoiTienDo.md` (20 hạng mục, cập nhật tới 05/09/2026) + `Template_Timeline_Tong_quan_08-08_den_21-11-2026.xlsx` | Cột "nhóm tự điền" (4) **để trống có chủ đích** — không điền thay |
| Giải thích tunnel SD-WAN | `Giai_thich_Tunnel_SD-WAN.md` | Tài liệu giải thích cho phần lý thuyết |
| Hướng dẫn vận hành | `HuongDan/` | Ryu/OVS, ký/add vEdge, phục hồi vEdge S100, xem GUI vManager |
| README/đề tài | `README.md`, `detai.md` | Tổng quan đề tài, người thực hiện |

Mốc: bảo vệ giả định cuối 11/2026 (timeline 08/08 → 21/11/2026).

## Quy tắc khi viết/sửa báo cáo và slide

1. **Nguồn dữ liệu kỹ thuật** theo thứ tự: `.unl` → `configs/` → `campus_network_sdn_sdwan.md` → `Chapter3/4/5.tex`. Ảnh và `md_content` trong `BAOCAO_DACNTT_LVT/prism-uploads/` là dữ liệu cũ (nhãn IP lỗi thời) — chỉ minh họa bố cục; đừng trích IP từ đó.
2. **Không tuyên bố kết quả chưa kiểm chứng.** Tách rõ `Đã hoàn thành / Đang thực hiện / Chưa thực hiện`. Trạng thái lấy từ `project-status.md` + kiểm live; không viết "hiệu quả X%" khi chưa có số liệu đo.
3. Bài học vận hành có giá trị đưa vào Chương 4/5 (chứng minh hiểu sâu, có bằng chứng): root cause DHCP 3 lớp (table-miss, tag 802.1Q trong packet-in, `dl_vlan` vs `vlan_vid`), loop VLAN 99 và cây quản trị, route /24 ECMP cho 2 màu TLOC, whitelist 3 controller, subject cert `O=Cisco Systems`, quyết định Firewall-as-Core, BGP underlay thay OSPF.
4. Đồng bộ thuật ngữ: giữ tiếng Anh cho thuật ngữ kỹ thuật (VLAN, OpenFlow, TLOC, OMP, BFD…); phần còn lại tiếng Việt học thuật.
5. Khi số liệu trong `.md`/`.tex` mâu thuẫn `.unl` (ví dụ số node, số link, node-id, System-IP): sửa tài liệu theo `.unl`, nêu rõ trong tóm tắt.
6. Ảnh topology chụp từ EVE-NG hiện hành nên thay thế ảnh Prism trong `BAOCAO_DACNTT_LVT/image/` khi có dịp.

## Biên dịch và kiểm tra

- Báo cáo: từ `BAOCAO_DACNTT_LVT/` chạy `pdflatex -halt-on-error main.tex` (2 lượt, thêm `bibtex main` khi đổi tài liệu tham khảo) — cần MiKTeX. Đọc `main.log` tìm `Overfull`, `undefined references`, `Citation … undefined`.
- Slide: `pdflatex` từ `SlideTrinhBayDA/`. Render trang vừa sửa sang ảnh và **xem trực quan**; dọn ảnh preview tạm sau khi kiểm.
- File sinh ra (`*.aux`, `*.log`, `main.pdf`…) đang được git theo dõi — chỉ commit PDF khi người dùng yêu cầu; tránh diff nhiễu.
- Skill `design-slides` (cục bộ ở `.codex/skills/design-slides/`, không track) có checklist Beamer/`check_slides.py` để tham khảo khi làm slide.

## Việc thường gặp

| Yêu cầu | Cách làm |
|---|---|
| "Cập nhật báo cáo theo tiến độ mới" | Đọc `project-status.md` + `git log`; sửa Chương 4/5 và slide chương 5; giữ 3 trạng thái hoàn thành/đang làm/chưa làm |
| "Cập nhật bảng tiến độ" | Sửa `BangTheoDoiTienDo.md` cột 4 hạng mục/thời gian/kết quả; **không** điền cột "nhóm tự điền" |
| "Thêm mục thiết kế" | Sửa `.md` (nguồn) trước, rồi báo cáo; nếu đổi node/link thì `.unl` + `configs/README.md` |
| "Chuẩn bị demo" | Kịch bản: mở lab → VPC nhận DHCP → ping liên site → cắt 1 màu WAN xem BFD/failover → mất controller thì OVS làm gì. Kiểm live từng bước trước ngày bảo vệ |
