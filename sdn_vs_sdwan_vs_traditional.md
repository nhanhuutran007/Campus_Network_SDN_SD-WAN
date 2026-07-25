# So sánh SDN vs SD-WAN vs Mạng Truyền thống

---

## 1. Bảng so sánh tổng quan

| Tiêu chí | Mạng Truyền thống | SDN (Software-Defined Networking) | SD-WAN (Software-Defined Wide Area Network) |
|---|---|---|---|
| **Khái niệm** | Mạng sử dụng thiết bị vật lý với cấu hình thủ công, mỗi thiết bị tự quản lý routing/switching | Kiến trúc tách biệt control plane và data plane, quản lý tập trung bằng phần mềm | Giải pháp quản lý WAN phần mềm, kết hợp nhiều loại đường truyền (Internet, MPLS, LTE) |
| **Mô hình quản lý** | Phân tán — cấu hình từng thiết bị riêng lẻ | Tập trung — quản lý toàn bộ mạng từ SDN Controller | Tập trung — quản lý từ cloud-based dashboard |
| **Control Plane** | Nhúng vào thiết bị vật lý (distributed) | Tách rời — đặt trên SDN Controller (centralized) | Tách rời — điều khiển bởi vSmart/vManage |
| **Data Plane** | Xử lý trên từng thiết bị | Xử lý trên thiết bị theo flow rules từ controller | Xử lý trên SD-WAN Edge / cEdge |
| **Cấu hình** | Thủ công qua CLI từng thiết bị | Template-based, push policies từ controller | Zero-Touch Provisioning (ZTP), template-based |
| **Tốc độ triển khai** | Chậm (tuần đến tháng) | Trung bình (ngày đến tuần) | Nhanh (phút đến giờ với ZTP) |
| **Chi phí WAN** | Cao — phụ thuộc MPLS | Trung bình — cần đầu tư controller | Thấp — tận dụng Internet giá rẻ kết hợp MPLS |
| **Tính linh hoạt** | Thấp — thay đổi cần can thiệp vật lý | Cao — thay đổi bằng phần mềm | Rất cao — tự động chọn tuyến tối ưu |
| **Khả năng mở rộng** | Hạn chế — thêm thiết bị = cấu hình thủ công | Mở rộng theo chiều ngang tốt | Rất tốt — thêm site chỉ cần cEdge + ZTP |
| **Visibility / Giám sát** | Giới hạn — SNMP, syslog riêng lẻ | Tốt — topology discovery, flow monitoring | Rất tốt — real-time dashboard, analytics |
| **Khả năng phục hồi** | Chậm — failover thủ công hoặc HSRP | Nhanh — controller tính toán lại đường đi | Rất nhanh — tự động failover giữa các link WAN |
| **Bảo mật** | ACL thủ công trên từng thiết bị | Policy-based, ACL tập trung | IPsec encryption on-overlay, segmentation |
| **Multi-tenancy** | Khó thực hiện | Hỗ trợ qua VLAN/VPN segmentation | Native multi-VPN support |

---

## 2. So sánh chi tiết theo từng khía cạnh

### 2.1. Kiến trúc (Architecture)

| Khía cạnh | Mạng Truyền thống | SDN | SD-WAN |
|---|---|---|---|
| **Mô hình** | Core → Distribution → Access | Giữ nguyên mô hình vật lý, bổ sung controller layer | Overlay network trên hạ tầng WAN hiện tại |
| **Control Plane** | Phân tán — mỗi router/switch tự quyết định | Centralized — SDN Controller quyết định | Centralized — vSmart điều khiển OMP |
| **Data Plane** | Hardware-based forwarding | Software-based (OpenFlow rules) | Software-based (OMP + IPsec) |
| **Management Plane** | CLI / SNMP / SSH từng thiết bị | REST API + Web GUI từ controller | vManage Dashboard (cloud-based) |
| **Protocol chính** | OSPF, STP, HSRP, BGP | OpenFlow 1.3+, NETCONF, gRPC | OMP (Overlay Management Protocol), DTLS |
| **Virtualization** | VLAN (Layer 2) | NFV (Network Functions Virtualization) | Full overlay — VPN segmentation on-any transport |

### 2.2. Quản lý & Vận hành (Management & Operations)

| Khía cạnh | Mạng Truyền thống | SDN | SD-WAN |
|---|---|---|---|
| **Zero-Touch Provisioning** | Không hỗ trợ | Hỗ trợ qua controller | Native — thiết bị tự cấu hình khi kết nối Internet |
| **Cấu hình thiết bị** | CLI thủ công (copy-paste scripts) | Template push từ controller | Template-based provisioning từ vManage |
| **Thay đổi mạng** | Manual — cần SSH vào từng switch | Software-defined — thay đổi từ controller | Software-defined — thay đổi policy từ dashboard |
| **Rollback** | Thủ công — reverse CLI commands | Version-controlled, rollback từ controller | Template versioning, instant rollback |
| **Monitoring** | SNMP polling, syslog phân tán | sFlow/NetFlow tập trung, topology maps | Real-time analytics, DPI (Deep Packet Inspection) |
| **Troubleshooting** | Ping, traceroute, packet capture thủ công | Controller visualization, path computation | Built-in: speed test, traceroute, packet capture |
| **Compliance / Audit** | Kiểm tra thủ công từng thiết bị | Policy compliance checking tự động | Audit logs tập trung từ vManage |

### 2.3. Hiệu năng & Tối ưu (Performance & Optimization)

| Khía cạnh | Mạng Truyền thống | SDN | SD-WAN |
|---|---|---|---|
| **Load balancing** | ECMP, Link aggregation thủ công | Centralized traffic engineering | Application-aware routing — tự động balance theo app |
| **Quality of Service (QoS)** | ACL/queue thủ công trên từng device | QoS policies push từ controller | QoS tự động — ưu tiên app quan trọng (VoIP, Video) |
| **Path selection** | Static routing hoặc OSPF/BGP | Controller tính toán path tối ưu | Real-time — chọn link tốt nhất cho từng application |
| **Failover** | HSRP/VRRP (L3), STP (L2) | Controller reroutes flows | Sub-second failover giữa Internet/MPLS/LTE |
| **Bandwidth utilization** | Thường under-utilize (1 link active) | Tốt hơn — controller optimize | Rất tốt — sử dụng đồng thời nhiều link WAN |
| **Latency optimization** | Không có | Tùy controller implementation | Forward Error Correction (FEC), packet duplication |

### 2.4. Bảo mật (Security)

| Khía cạnh | Mạng Truyền thống | SDN | SD-WAN |
|---|---|---|---|
| **Encryption** | VPN site-to-site thủ công | Overlay encryption via controller | IPsec tunnel on-overlay, mã hóa toàn bộ traffic |
| **Micro-segmentation** | VLAN + ACL (coarse-grained) | Flow-based micro-segmentation | VPN-based segmentation (multi-tenant) |
| **Policy enforcement** | ACL trên từng thiết bị | Centralized ACL từ controller | Centralized policy từ vManage, push đến mọi site |
| **Zero Trust** | Phức tạp để implement | Hỗ trợ tốt qua flow-level control | Hỗ trợ — mỗi site/VPN là segment riêng |
| **Threat detection** | IDS/IPS riêng biệt | Controller có thể tích hợp threat intel | Cloud-based security tích hợp (Umbrella, Zscaler) |
| **NAT Traversal** | Thủ công cấu hình | Controller hỗ trợ | vBond tự động — STUN/TURN |

### 2.5. Chi phí (Cost)

| Khía cạnh | Mạng Truyền thống | SDN | SD-WAN |
|---|---|---|---|
| **CapEx (ban đầu)** | Cao — managed switches/routers | Trung bình — controller + OpenFlow switches | Thấp đến TB — Edge device + subscription |
| **OpEx (vận hành)** | Cao — cần team CLI-expert | Trung bình — cần SDN expertise | Thấp — tự động hóa cao, reduced CLI |
| **WAN cost** | Cao — MPLS dominant | Không trực tiếp ảnh hưởng | Thấp — thay MPLS bằng Internet, tiết kiệm 50-90% |
| **Vendor lock-in** | Cao — proprietary protocols | Thấp hơn — open standards (OpenFlow) | Trung bình — Cisco Viptela, VMware VeloCloud |
| **ROI timeline** | — | 6-18 tháng | 3-12 tháng |

### 2.6. Triển khai & Ứng dụng (Deployment & Use Cases)

| Khía cạnh | Mạng Truyền thống | SDN | SD-WAN |
|---|---|---|---|
| **Campus Network** | Truyền thống — widely deployed | Next-gen campus (Cisco ACI, Aruba Central) | Bổ sung cho campus WAN edge |
| **Data Center** | Traditional 3-tier or spine-leaf | **Primary use case** — NSX, ACI, OpenStack | Không trực tiếp applicable |
| **WAN / Branch** | MPLS + static routing | Không phải primary focus | **Primary use case** — thay thế MPLS |
| **Cloud connectivity** | IPsec VPN thủ công | Controller-mediated cloud connect | Native cloud on-ramp (AWS, Azure, GCP) |
| **Remote workforce** | VPN concentrator thủ công | — | Integrated remote access |
| **IoT / Edge computing** | Khó quản lý quy mô lớn | Micro-segmentation helps | Edge computing integration |

---

## 3. Khi nào dùng giải pháp nào?

| Kịch bản | Giải pháp phù hợp | Lý do |
|---|---|---|
| **Campus network nội bộ** (1 tòa nhà) | SDN | Quản lý tập trung VLAN, ACL, QoS cho campus |
| **WAN đa site** (nhiều chi nhánh) | SD-WAN | Tiết kiệm chi phí MPLS, ZTP, failover tự động |
| **Data Center** | SDN | Micro-segmentation, NFV, automation |
| **Mạng SMB đơn giản** (< 10 switch) | Truyền thống + SD-WAN | Đơn giản, chi phí thấp, SD-WAN cho WAN |
| **Doanh nghiệp lớn** (campus + branches) | **SDN + SD-WAN** | SDN cho campus, SD-WAN cho WAN — best of both worlds |
| **Migrating từ MPLS sang Internet** | SD-WAN | Gradual migration, dual-overlay |

---

## 4. Sơ đồ so sánh kiến trúc

```
MẠNG TRUYỀN THỐNG:
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Router A    │◄──►│  Router B    │◄──►│  Router C    │
│  (CLI config)│    │  (CLI config)│    │  (CLI config)│
└──────────────┘    └──────────────┘    └──────────────┘
  Mỗi thiết bị tự quản lý — Phân tán


SDN:
┌─────────────────────────────┐
│     SDN Controller          │  ◄── Control Plane (Tập trung)
│  (ONOS / OpenDaylight)      │
└─────────┬───────────────────┘
          │ OpenFlow
┌─────────▼───────────────────┐
│  ┌────────┐ ┌────────┐     │  ◄── Data Plane
│  │Switch A│ │Switch B│ ... │
│  └────────┘ └────────┘     │
└─────────────────────────────┘


SD-WAN:
┌─────────────────────────────┐
│  vManage  vSmart  vBond     │  ◄── Control/Management (Cloud)
│  (AWS US West)              │
└──┬──────────┬───────────┬───┘
   │ OMP/DTLS │           │
┌──▼──┐  ┌───▼──┐  ┌─────▼──┐
│Edge1│  │Edge2 │  │Edge3   │  ◄── Overlay (MPLS + Internet)
│Site1│  │Site2 │  │Site3   │
└─────┘  └──────┘  └────────┘
```

---

## 5. Tổng kết

| | Mạng Truyền thống | SDN | SD-WAN |
|---|---|---|---|
| **Điểm mạnh** | Đơn giản, ổn định, đã được chứng minh | Tự động hóa cao, programmable, mở rộng tốt | Tiết kiệm chi phí WAN, triển khai nhanh, thông minh |
| **Điểm yếu** | Thủ công, chậm, chi phí WAN cao | Phức tạp, cần đội ngũ chuyên môn cao | Vendor-specific, phụ thuộc cloud controller |
| **Tương lai** | Dần được thay thế trong môi trường phức tạp | Tiếp tục phát triển mạnh trong DC & Campus | Trở thành standard cho WAN hiện đại |
