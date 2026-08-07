---
name: campus-network-lab
description: Hỗ trợ phân tích, cấu hình, đồng bộ và kiểm tra dự án Campus Network kết hợp SDN, SD-WAN trên EVE-NG. Dùng khi làm việc với campus_network_sdn_sdwan.md, Campus Network SDN SD-WAN.unl, configs/, Ryu/OpenFlow/OVS, Core/ASAv/vEdge/VPC/DHCP, node-id, địa chỉ IP, cấu hình nhúng EVE-NG, triển khai lab hoặc xử lý lỗi node.
---

# Campus Network Lab

## Mục tiêu

Làm việc an toàn và nhất quán trên repository mô phỏng bốn campus bằng SDN/OpenFlow và SD-WAN. Tra cứu dữ liệu hiện tại trong repository thay vì dựa vào trạng thái phiên cũ ghi trong skill.

Trả lời và cập nhật tài liệu bằng tiếng Việt; giữ thuật ngữ kỹ thuật bằng tiếng Anh.

## Bắt đầu mỗi tác vụ

1. Xác định project root bằng `campus_network_sdn_sdwan.md`, `Campus Network SDN SD-WAN.unl` và `configs/`.
2. Chạy `git status --short` và bảo toàn mọi thay đổi hiện có của người dùng.
3. Đọc đúng nguồn liên quan trước khi kết luận:
   - Đọc `campus_network_sdn_sdwan.md` cho thiết kế, IP, VLAN và bảng liên kết.
   - Đọc `configs/README.md` cho ánh xạ thiết bị/node-id, thứ tự boot và thao tác config.
   - Đọc file dưới `configs/` cho cấu hình thực thi.
   - Phân tích file `.unl` cho topology và config nhúng thực tế.
4. Nếu các nguồn mâu thuẫn, báo rõ mâu thuẫn và kiểm chứng từ artifact thực tế. Không tự chọn dữ liệu cũ chỉ vì nó xuất hiện trong skill.

## Chọn tài liệu tham chiếu

- Đọc [project-conventions.md](references/project-conventions.md) khi xử lý kiến trúc, IP, VLAN, node-id hoặc quyết định thiết kế.
- Đọc [eve-ng-workflows.md](references/eve-ng-workflows.md) trước khi sửa `.unl`, nhúng config, deploy lên EVE-NG, wipe/start node hoặc xử lý `.lock`.
- Đọc [ryu-ovs-recovery.md](references/ryu-ovs-recovery.md) trước khi triển khai, khởi động lại hoặc khôi phục kết nối Ryu–OVS của Site 100.
- Chạy `python .codex/skills/campus-network-lab/scripts/validate_unl.py "Campus Network SDN SD-WAN.unl"` sau mọi thay đổi tới `.unl` hoặc startup config nhúng.

## Quy trình thay đổi

1. Xác định phạm vi ảnh hưởng trước khi sửa.
2. Sửa nguồn cấu hình trong `configs/`.
3. Đồng bộ các artifact phụ thuộc:
   - Thay đổi thiết kế/IP/link: cập nhật tài liệu thiết kế.
   - Thay đổi node-id hoặc cách deploy: cập nhật `configs/README.md`.
   - Thay đổi topology: cập nhật duy nhất `Campus Network SDN SD-WAN.unl`.
   - Thay đổi startup config của node tự nạp: cập nhật cả file nguồn và `<configs>` nhúng trong `.unl`.
4. Chạy kiểm tra chuyên biệt, rồi xem lại `git diff` chỉ cho các file thuộc phạm vi.
5. Tóm tắt file đã đổi, kiểm tra đã chạy và việc thủ công còn lại.

## Nguyên tắc an toàn

- Không tạo lại `.unl.bak`; không sửa bản `.unl` khác ngoài file chính.
- Không commit, push, SCP, wipe, start/stop node hoặc thay đổi EVE-NG từ xa nếu người dùng chưa yêu cầu hành động đó.
- Không lưu mật khẩu, token hoặc thông tin xác thực vào skill, repository, lệnh shell hay log. Yêu cầu người dùng cung cấp bí mật theo từng phiên khi thật sự cần kết nối.
- Trước thao tác có thể làm mất lab state, xác nhận đúng lab, node-id và đường dẫn; ưu tiên tác động từng node.
- Khi thay đổi một invariant đã được phê duyệt, cập nhật đồng thời tài liệu tham chiếu và validator thay vì bỏ qua lỗi kiểm tra.

## Tiêu chí hoàn tất

- XML hợp lệ, node/network reference không treo và config nhúng khớp node bật `config="1"`.
- Thiết kế, topology, file cấu hình và bảng node-id không mâu thuẫn trong phạm vi thay đổi.
- Không làm mất hoặc ghi đè thay đổi không liên quan của người dùng.
- Nêu rõ phần nào chỉ có thể xác minh trên EVE-NG thật.
