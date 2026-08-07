---
name: design-slides
description: Thiết kế, tái cấu trúc, chỉnh sửa và kiểm tra slide thuyết trình; ưu tiên LaTeX Beamer và PDF đầu ra. Dùng khi cần xây dựng dàn ý, tinh gọn nội dung, thiết kế theme/header/footer, căn chỉnh chữ-hình-bảng, chèn ảnh, sửa tràn khung, thay đổi thứ tự trang, biên dịch hoặc rà soát trực quan bộ slide.
---

# Thiết kế slide

## Mục tiêu

Tạo bộ slide có mạch kể chuyện rõ, mật độ nội dung vừa phải, hệ thống thị giác nhất quán và PDF đã được kiểm tra trực quan. Giữ thuật ngữ kỹ thuật bằng tiếng Anh khi cách dịch làm giảm độ chính xác.

## Chọn tài liệu tham chiếu

- Đọc `references/beamer-guidelines.md` trước khi sửa LaTeX Beamer, theme, frame, ảnh hoặc bảng.
- Đọc `references/review-checklist.md` trước lượt kiểm tra bàn giao của mọi bộ slide.
- Chạy `scripts/check_slides.py` với file `.tex` gốc sau khi chỉnh Beamer.

## Quy trình thực hiện

### 1. Xác định nguồn và bảo toàn thay đổi

1. Tìm file nguồn, ảnh, theme và PDF hiện có bằng `rg --files`.
2. Chạy `git status --short`; không ghi đè thay đổi ngoài phạm vi.
3. Đọc file gốc điều phối toàn bộ deck và chỉ các chapter/frame liên quan.
4. Xác định loại báo cáo, người nghe, thời lượng và kết quả người dùng muốn truyền đạt. Suy luận hợp lý từ tài liệu nếu chưa được nêu.

### 2. Thiết kế mạch nội dung

1. Viết một câu thông điệp chính cho toàn bộ deck.
2. Sắp xếp section theo quan hệ vấn đề → cơ sở → đề xuất → trạng thái/kết quả → kết luận.
3. Chỉ giữ một ý chính trên mỗi slide; mỗi slide phải trả lời được “người nghe cần nhớ gì?”.
4. Cắt chi tiết thao tác, lệnh và dữ liệu phụ khỏi slide chính; chuyển vào phụ lục nếu thật sự cần.
5. Với báo cáo tiến độ, tách rõ `Đã hoàn thành`, `Đang thực hiện`, `Chưa thực hiện`; không trình bày hiệu quả như kết quả đã kiểm chứng khi chưa có số liệu.

### 3. Áp dụng hệ thống thị giác

1. Giữ nhất quán tỷ lệ, palette, font, header, footer, lề và cách đánh số.
2. Dùng grid để căn hàng; ưu tiên khoảng trắng hơn việc lấp đầy khung.
3. Tạo phân cấp rõ giữa tiêu đề, nhãn nhóm, nội dung và chú thích.
4. Dùng tối đa một thành phần nhấn chính trên mỗi slide.
5. Giữ theme hiện có khi người dùng chỉ yêu cầu chỉnh nội dung hoặc một thành phần cục bộ.

### 4. Chỉnh source

1. Dùng `apply_patch` cho thay đổi thủ công.
2. Đặt frame mới đúng vị trí ngữ nghĩa, không dựa duy nhất vào số trang cũ.
3. Kiểm tra ảnh bằng công cụ xem ảnh trước khi chèn; dùng đường dẫn tương đối và `keepaspectratio`.
4. Không kéo giãn ảnh, không cắt mất nhãn quan trọng và không bịa nguồn ảnh.
5. Escape ký tự đặc biệt của LaTeX; giữ tên file và label ổn định khi không cần đổi.
6. Khi đổi số frame hoặc mục lục, biên dịch ít nhất hai lượt.

### 5. Kiểm tra kỹ thuật và trực quan

1. Biên dịch với chế độ dừng khi có lỗi; không xem việc source hợp lệ là đủ.
2. Chạy:

   `python .codex/skills/design-slides/scripts/check_slides.py <path-to-main.tex>`

3. Xử lý lỗi thiếu file/ảnh và cảnh báo tràn khung trước khi bàn giao.
4. Render các trang vừa thay đổi từ PDF sang ảnh và xem trực quan ở kích thước đọc thực tế.
5. Kiểm tra vị trí trang, căn lề, độ tương phản, cỡ chữ, tỷ lệ ảnh, footer và tổng số trang.
6. Xóa ảnh preview tạm do mình tạo sau khi kiểm tra.

## Tiêu chí hoàn tất

- Thứ tự slide đúng với mạch nội dung và yêu cầu vị trí của người dùng.
- Không có nội dung ngoài phạm vi hoặc tuyên bố chưa được tài liệu hỗ trợ.
- Không có chữ/hình/bảng bị che, cắt hoặc tràn khung.
- Ảnh rõ, đúng tỷ lệ và có chú thích/nguồn khi thông tin nguồn sẵn có.
- PDF biên dịch thành công; bookmark, mục lục, số trang và tổng số trang đã cập nhật.
- Bàn giao đường dẫn source đã đổi, PDF đầu ra, số trang và kiểm tra đã chạy.
