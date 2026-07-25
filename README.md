# Xây dựng mạng Campus Network sử dụng SDN và SD-WAN

## 👥 Người thực hiện
- **Trần Hữu Nhân** - MSSV: `52300235`
- **Nguyễn Nhật Hào** - MSSV: `52300198`

---

## 📌 Mở đầu và Tổng quan đề tài

### 1. Lý do chọn đề tài
Trong môi trường đại học, hệ thống mạng Campus là hạ tầng nền tảng phục vụ các hoạt động học tập, giảng dạy, nghiên cứu, quản trị hành chính và cung cấp dịch vụ số. Khi số lượng khoa, phòng học, phòng máy, thiết bị không dây và các cơ sở phụ tăng lên, mô hình mạng cần đáp ứng đồng thời các yêu cầu về hiệu năng, bảo mật, khả năng quản lý và mở rộng.

Các hệ thống mạng truyền thống thường được cấu hình trực tiếp trên từng thiết bị, khiến quá trình thay đổi VLAN, bổ sung khu vực mạng, triển khai chính sách truy cập hoặc xử lý sự cố mất nhiều thời gian. Vì vậy, việc kết hợp kiến trúc Campus phân cấp với SDN và SD-WAN là hướng tiếp cận phù hợp nhằm tăng khả năng quản lý tập trung, tự động hóa vận hành và kết nối linh hoạt giữa nhiều địa điểm.

### 2. Mục tiêu thực hiện đề tài
Đề tài hướng đến việc xây dựng khung thiết kế mạng Campus Network sử dụng SDN và SD-WAN phù hợp với môi trường trường đại học. Các mục tiêu chính bao gồm:
- Thiết kế kiến trúc mạng Campus theo mô hình Core – Distribution – Access.
- Phân hoạch VLAN và địa chỉ IP cho các khoa, phòng học, phòng máy, khu vực hành chính và dịch vụ dùng chung.
- Đề xuất phương án quản lý tập trung thiết bị mạng bằng SDN Controller.
- Xây dựng phương án kết nối Campus chính với các cơ sở phụ thông qua SD-WAN.
- Xác định các tiêu chí đánh giá về khả năng vận hành, dự phòng, mở rộng và quản lý chính sách.

### 3. Đối tượng và phạm vi nghiên cứu
- **Đối tượng nghiên cứu:** Hệ thống mạng Campus trong môi trường đào tạo, bao gồm các thiết bị chuyển mạch, định tuyến, phân vùng VLAN, dịch vụ cấp phát địa chỉ, chính sách truy cập và kết nối WAN giữa nhiều cơ sở.
- **Phạm vi thực hiện:** Tập trung vào thiết kế logic và mô hình triển khai ở mức dự án, chưa đi sâu vào triển khai trên toàn bộ hạ tầng vật lý thực tế. Các nội dung chính bao gồm mô hình topology, phân hoạch mạng, vai trò của SDN Controller, kết nối SD-WAN và các kịch bản kiểm thử chức năng cơ bản.

### 4. Phương pháp nghiên cứu
Đề tài được thực hiện theo hướng kết hợp nghiên cứu lý thuyết và thiết kế mô hình triển khai:
- **Lý thuyết:** Tập trung vào kiến trúc mạng Campus, VLAN, định tuyến nội bộ, SDN, SD-WAN và các cơ chế bảo mật cơ bản.
- **Thiết kế mô hình:** Tập trung xây dựng topology, bảng VLAN, sơ đồ địa chỉ, chính sách truy cập và quy trình kiểm thử.

### 5. Ý nghĩa thực tiễn của đề tài
Mô hình đề xuất giúp đơn giản hóa quá trình quản trị mạng Campus, giảm phụ thuộc vào cấu hình thủ công trên từng thiết bị và tăng khả năng mở rộng khi nhà trường bổ sung khoa, phòng học hoặc cơ sở mới. Việc tích hợp SDN và SD-WAN cũng tạo nền tảng cho các hướng phát triển như tự động hóa cấu hình, giám sát tập trung, tối ưu lưu lượng và quản lý chính sách bảo mật theo khu vực chức năng.

---

## ⚡ 6. Điểm nổi bật & Tính đột phá của Đề tài

- 🌐 **Kiến trúc Mạng Lai (Hybrid SDN + SD-WAN):** Kết hợp quản trị tập trung mạng nội bộ Campus (LAN) bằng SDN Controller và quản trị kết nối đa cơ sở/chi nhánh (WAN) bằng SD-WAN Overlay.
- ⚡ **Zero-Touch Provisioning (ZTP) & Template Push:** Cho phép mở rộng thêm chi nhánh mới hoặc hạ tầng phòng máy một cách nhanh chóng chỉ trong vài phút mà không cần cấu hình thủ công qua CLI.
- 🛡️ **Micro-segmentation & Phân hoạch đa lớp:** Phân vùng mạng chi tiết giữa sinh viên, giảng viên, hành chính, phòng máy lab và khách (Guest WiFi), áp dụng chính sách bảo mật (Centralized ACL) ngay từ Controller.
- 🔄 **Khả năng dự phòng & Tin cậy cao (High Availability):** Thiết lập VRRP Active/Standby tại Core Layer, EtherChannel/LACP giữa các tầng và tự động chuyển mạch kết nối WAN (Sub-second failover) giữa Internet và MPLS khi xảy ra sự cố.
- 📊 **Giám sát trực quan & Tự động hóa (Centralized Visibility):** Tích hợp công cụ giám sát Prometheus & Grafana cùng bảng điều khiển SDN/SD-WAN Controller, giúp phát hiện sự cố và điều phối lưu lượng thời gian thực.

---

## 🛠️ 7. Công nghệ & Giao thức cốt lõi

| Phân vùng | Công nghệ / Giao thức | Vai trò & Chức năng |
|---|---|---|
| **SDN Controller** | ONOS / OpenDaylight | Quản lý tập trung Control Plane cho Campus LAN, quản lý Flow Rules, Topology discovery qua OpenFlow 1.3 / RESTCONF. |
| **SD-WAN Control Plane** | Cisco SD-WAN (vManage, vSmart, vBond) | Quản lý overlay WAN, điều phối định tuyến OMP, cấp phát IPsec tunnel tự động cho các chi nhánh. |
| **Core & Aggregation** | L3 Switching, OSPF Area 0, VRRP | Định tuyến tốc độ cao, dự phòng gateway cho toàn mạng Campus chính (Site 100). |
| **Bảo mật & Phân vùng** | 802.1Q VLAN, IPsec Encryption, Centralized ACL | Mã hóa toàn bộ dữ liệu WAN qua IPsec, phân tách traffic giữa các khoa/phòng ban. |
| **Giám sát & Quản lý** | Prometheus, Grafana, sFlow / NetFlow | Thu thập metric, giám sát băng thông và cảnh báo sự cố tập trung. |

---

## 💡 8. Bảng so sánh giải pháp đề xuất với Mạng Truyền thống

| Tiêu chí | Mạng Campus Truyền Thống | Giải Pháp SDN + SD-WAN Đề Xuất |
|---|---|---|
| **Mô hình quản lý** | Cấu hình phân tán thủ công từng thiết bị (CLI) | Quản lý tập trung qua SDN/SD-WAN Controller (GUI/API) |
| **Tốc độ mở rộng** | Chậm (cần cấu hình lại switch/router từng phòng) | Nhanh chóng (ZTP + Template Push từ Controller) |
| **Phản ứng sự cố WAN** | Chuyển mạch định tuyến chậm, cần can thiệp thủ công | Tự động chuyển tuyến tối ưu (Application-Aware Routing) trong < 1s |
| **Kiểm soát bảo mật** | ACL phân tán, khó đồng bộ chính sách | Chính sách bảo mật tập trung (Centralized Security Policy) |
