# Hướng dẫn LaTeX Beamer

## Mục lục

- Khảo sát source
- Bố cục và mật độ
- Mẫu frame
- Ảnh và bảng
- Header và footer
- Biên dịch
- Lỗi thường gặp

## Khảo sát source

- Xác định file gốc chứa `\documentclass`, các lệnh `\input` và thiết lập theme.
- Xác định thư mục được dùng làm working directory khi biên dịch; đường dẫn ảnh được giải quyết từ đây.
- Đọc frame đứng trước và sau vị trí chỉnh để giữ cách đánh số và mạch nội dung.
- Không sửa đồng loạt theme nếu yêu cầu chỉ liên quan một frame.

## Bố cục và mật độ

- Ưu tiên tỷ lệ `aspectratio=169` cho trình chiếu màn hình.
- Mỗi slide nên có một tiêu đề ngắn và một thông điệp chính.
- Giữ khoảng 3–5 bullet cấp một; tránh bullet dài hơn hai dòng.
- Dùng hai cột khi hai nhóm thông tin có quan hệ so sánh hoặc song song.
- Dùng bảng cho ánh xạ chính xác; tránh bảng có quá nhiều cột hẹp.
- Không dùng `\scriptsize` để ép một slide quá tải, trừ chú thích hoặc bảng ngắn.

## Mẫu frame

### Ảnh toàn trang nội dung

```tex
\begin{frame}{Tiêu đề hình minh họa}
    \centering
    \includegraphics[
        width=0.9\textwidth,
        height=0.72\textheight,
        keepaspectratio
    ]{images/example.jpg}

    \vspace{0.1cm}
    {\scriptsize\textit{Hình: Chú thích ngắn gọn}}
\end{frame}
```

### Hai cột cân bằng

```tex
\begin{frame}{Tiêu đề}
    \begin{columns}[T]
        \column{0.48\textwidth}
        \textbf{Nhóm thứ nhất}
        \begin{itemize}
            \item Ý chính.
        \end{itemize}

        \column{0.48\textwidth}
        \textbf{Nhóm thứ hai}
        \begin{itemize}
            \item Ý chính.
        \end{itemize}
    \end{columns}
\end{frame}
```

### Khối nhấn

```tex
\begin{block}{Thông điệp chính}
    Một câu kết luận mà người nghe cần ghi nhớ.
\end{block}
```

Chỉ dùng block khi nó tạo phân cấp rõ; không bọc mọi đoạn văn trong block.

## Ảnh và bảng

- Xem ảnh gốc và kiểm tra kích thước trước khi chèn.
- Dùng `width` cùng `height` và `keepaspectratio` để giới hạn cả hai chiều.
- Ưu tiên PNG cho sơ đồ/chữ nhỏ, JPEG cho ảnh chụp, PDF/SVG đã chuyển đổi phù hợp cho vector.
- Giữ chữ trong ảnh đủ đọc khi trình chiếu; phóng ảnh hoặc tách thành nhiều slide nếu cần.
- Với bảng, giảm nội dung trước khi giảm font; dùng `p{...}` cho cột văn bản dài.
- Căn số theo cùng đơn vị và không dùng màu làm tín hiệu duy nhất.

## Header và footer

- Căn tiêu đề theo toàn bộ chiều rộng thanh header, không tính icon/vạch trang trí vào chiều rộng chữ.
- Đặt thành phần trang trí bằng lớp overlay độc lập để tránh chồng chữ.
- Giữ footer thấp, tương phản đủ và thống nhất định dạng `trang/tổng trang`.
- Sau khi thay đổi frame, biên dịch hai lượt để cập nhật navigation và tổng trang.

## Biên dịch

Từ thư mục chứa file gốc:

```powershell
pdflatex --quiet -interaction=nonstopmode -halt-on-error main.tex
pdflatex --quiet -interaction=nonstopmode -halt-on-error main.tex
```

Nếu dự án dùng `latexmk`, ưu tiên lệnh build đã có trong repository.

Kiểm tra log:

```powershell
rg -n 'Overfull|Underfull|LaTeX Font Warning|Package hyperref Warning|pdfTeX warning' main.log
```

## Lỗi thường gặp

- `Overfull \hbox/\vbox`: rút gọn nội dung, tăng chiều rộng cột hoặc tách slide; không chỉ giảm font.
- `Underfull \hbox`: dùng câu ngắn hơn hoặc căn trái cột văn bản hẹp.
- Ảnh không tìm thấy: kiểm tra working directory và đường dẫn tương đối từ file gốc.
- Tiêu đề lệch: tách vạch/icon trang trí khỏi hộp chữ bằng overlay.
- Footer còn tổng trang cũ: biên dịch lại lượt thứ hai.
- Chữ trong hình quá nhỏ: tăng diện tích ảnh hoặc dùng phiên bản độ phân giải cao hơn.
