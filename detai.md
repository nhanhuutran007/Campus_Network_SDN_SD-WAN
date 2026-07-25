# ĐỀ TÀI: THIẾT KẾ CAMPUS NETWORK SỬ DỤNG SDN VÀ SD-WAN CHO MÔI TRƯỜNG ĐẠI HỌC

---

## 1. Bối cảnh vấn đề

### 1.1. Tình hình hiện tại

Trong môi trường đại học, hệ thống mạng Campus là hạ tầng nền tảng phục vụ các hoạt động:

- **Giảng dạy**: Kết nối phòng học, phòng máy tính, hệ thống e-learning
- **Nghiên cứu**: Truy cập cơ sở dữ liệu, tài nguyên số, hợp tác nghiên cứu
- **Quản trị hành chính**: Hệ thống email, quản lý sinh viên, tài chính
- **Dịch vụ số**: WiFi campus, cổng thông tin, ứng dụng di động

### 1.2. Thách thức của mô hình mạng truyền thống

| Thách thức | Mô tả |
|---|---|
| **Quản lý phân tán** | Mỗi switch, router phải cấu hình thủ công qua CLI → mất thời gian, dễ sai sót |
| **Khó mở rộng** | Thêm khoa/phòng học mới cần cấu hình lại VLAN, ACL trên nhiều thiết bị |
| **Xử lý sự cố chậm** | Khó xác định nguyên nhân gốc, thời gian downtime cao |
| **Chi phí vận hành** | Đội ngũ quản trị phải duy trì cấu hình trên từng thiết bị riêng lẻ |
| **Bảo mật kém** | ACL thủ công, khó kiểm soát truy cập theo thời gian thực |
| **WAN đắt đỏ** | MPLS cho liên kết giữa các cơ sở phụ tốn kém, bandwidth hạn chế |

### 1.3. Động lực thay đổi

- **Số lượng thiết bị tăng**: WiFi, IoT, BYOD đòi hỏi quản lý tập trung
- **Yêu cầu bảo mật nghiêm ngặt**: GDPR, quy định bảo mật dữ liệu giáo dục
- **Chuyển đổi số**: Ứng dụng điện toán đám mây, hybrid cloud
- **Tiết kiệm chi phí**: WAN cost optimization thông qua SD-WAN

---

## 2. Mục tiêu đề tài

### 2.1. Mục tiêu tổng quan

Xây dựng khung thiết kế mạng Campus Network sử dụng SDN và SD-WAN phù hợp với môi trường trường đại học, hướng tới mô hình mạng **tự động hóa, tập trung và mở rộng linh hoạt**.

### 2.2. Mục tiêu cụ thể

| STT | Mục tiêu | Mô tả chi tiết |
|---|---|---|
| 1 | **Thiết kế kiến trúc Campus** | Xây dựng mô hình 3 lớp Core – Distribution – Access cho campus chính |
| 2 | **Phân hoạch VLAN & IP** | Thiết kế VLAN và địa chỉ IP cho các khoa, phòng học, khu hành chính, server zone |
| 3 | **Triển khai SDN Controller** | Đề xuất phương án quản lý tập trung bằng SDN Controller (ONOS/OpenDaylight) |
| 4 | **Kết nối SD-WAN** | Xây dựng phương án liên kết campus chính với các chi nhánh qua SD-WAN |
| 5 | **Bảo mật & Chính sách** | Thiết kế ACL, firewall rules, phân quyền truy cập theo VLAN/khu vực |
| 6 | **Đánh giá & Kiểm thử** | Xác định tiêu chí đánh giá khả năng vận hành, dự phòng, mở rộng |

---

## 3. Định hướng nghiên cứu

### 3.1. Hướng tiếp cận

Đề tài đi theo hướng **kết hợp nghiên cứu lý thuyết và thiết kế mô hình triển khai**:

```
Nghiên cứu lý thuyết          Thiết kế mô hình          Kiểm thử
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ • Kiến trúc      │     │ • Topology       │     │ • Ping/Traceroute│
│ • VLAN, Routing  │────►│ • Bảng VLAN/IP   │────►│ • Failover test  │
│ • SDN, SD-WAN    │     │ • Chính sách ACL │     │ • Bandwidth test │
│ • Bảo mật        │     │ • Sơ đồ WAN     │     │ • Recovery test  │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### 3.2. Phạm vi nghiên cứu

| Nội dung | Phạm vi |
|---|---|
| **Đối tượng** | Hệ thống mạng Campus trong môi trường đào tạo (switch, router, VLAN, DHCP, WAN) |
| **Phạm vi** | Thiết kế logic và mô hình triển khai ở mức dự án |
| **Không bao gồm** | Triển khai trên hạ tầng vật lý thực tế, cấu hình hardware-specific |

### 3.3. Phương pháp nghiên cứu

- **Nghiên cứu tài liệu**: Kiến thức mạng, SDN, SD-WAN, best practices
- **Thiết kế mô hình**: Xây dựng topology, bảng VLAN, sơ đồ địa chỉ
- **Mô phỏng**: Sử dụng các công cụ mô phỏng mạng để kiểm thử
- **Đánh giá**: So sánh với mô hình truyền thống, phân tích ưu nhược điểm

---

## 4. Đề xuất giải pháp

### 4.1. Giải pháp tổng thể

Sử dụng kết hợp **SDN cho Campus nội bộ** và **SD-WAN cho liên kết đa site**:

```
┌─────────────────────────────────────────────────────────┐
│                    ĐẠI HỌC                              │
│                                                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │ SDN         │    │  Campus     │    │  Server     │ │
│  │ Controller  │◄──►│  Core Layer │◄──►│  Zone       │ │
│  │ (ONOS/ODL)  │    │  (OSPF/VRRP)│    │  (FTP, WEB) │ │
│  └──────┬──────┘    └──────┬──────┘    └─────────────┘ │
│         │                  │                           │
│         │         ┌────────┴────────┐                  │
│         │         │  Distribution   │                  │
│         │         │  Layer (VLAN)   │                  │
│         │         └────────┬────────┘                  │
│         │                  │                           │
│         │         ┌────────┴────────┐                  │
│         │         │   Access Layer  │                  │
│         │         │   (DHCP, PCs)   │                  │
│         │         └─────────────────┘                  │
│         │                                              │
│  ┌──────┴──────┐                                       │
│  │  cEdge      │──── Internet + MPLS ──── ┌─────────┐ │
│  │ (SD-WAN)    │                          │ Chi nhánh│ │
│  └─────────────┘                          │ Đà Nẵng  │ │
│                                           │ Cần Thơ  │ │
│                                           └─────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 4.2. Các thành phần chính

| Thành phần | Vai trò | Công nghệ |
|---|---|---|
| **SDN Controller** | Quản lý tập trung VLAN, ACL, QoS | ONOS / OpenDaylight |
| **Core Layer** | Định tuyến nội bộ, dự phòng | OSPF, VRRP, EtherChannel |
| **Distribution Layer** | Phân vùng VLAN, STP | VLAN, RSTP |
| **Access Layer** | Kết nối đầu cuối, cấp IP | DHCP, 802.1X |
| **SD-WAN Edge** | Liên kết đa site | Cisco vEdge/cEdge |
| **WAN Transport** | Truyền tải giữa các site | Internet + MPLS |

### 4.3. Phân hoạch mạng đề xuất

| Site | Site ID | VLAN | Khoa/Phòng |
|---|---|---|---|
| **Campus chính (RTP)** | 100 | 10, 20, 30, 40 | CNTT, Toán TK, Luật, Hành chính |
| **Chi nhánh Đà Nẵng** | 200 | 50, 60 | Kinh tế, Du lịch |
| **Chi nhánh Cần Thơ** | 300 | 70, 80 | Y tế, Nông nghiệp |

---

## 5. Ý nghĩa thực tiễn

| Lĩnh vực | Ý nghĩa |
|---|---|
| **Quản trị mạng** | Đơn giản hóa quá trình quản trị, giảm phụ thuộc cấu hình thủ công |
| **Mở rộng** | Dễ dàng bổ sung khoa, phòng học hoặc cơ sở mới |
| **Bảo mật** | Quản lý chính sách truy cập tập trung, phân vùng theo khu vực |
| **Chi phí** | Tiết kiệm WAN cost (50-90%) thông qua SD-WAN |
| **Tự động hóa** | Nền tảng cho giám sát tập trung, tối ưu lưu lượng, provisioning tự động |
| **Học thuật** | Tài liệu tham khảo cho các đề tài mạng tương tự |

---

## 6. Kết quả mong đợi

- **Bản thiết kế topology** campus network theo mô hình 3 lớp
- **Bảng phân hoạch VLAN** và quy hoạch địa chỉ IP chi tiết
- **Sơ đồ SD-WAN** liên kết campus chính với các chi nhánh
- **Chính sách bảo mật** (ACL, firewall rules) theo từng khu vực
- **Kịch bản kiểm thử** các chức năng cơ bản
- **Đánh giá** so sánh với mô hình mạng truyền thống
