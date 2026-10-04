# Kịch bản thuyết trình — Báo cáo tiến độ tuần 28/09 – 04/10/2026

**Đề tài:** Xây dựng mạng Campus Network sử dụng SDN và SD-WAN
**Nhóm:** Trần Hữu Nhân (52300235) — Nguyễn Nhật Hào (52300198)
**Slide:** `report.pdf` (20 slide) · **Thời lượng dự kiến:** 15–17 phút + hỏi đáp

> Cách dùng: phần **Nói** là lời thoại gợi ý, đọc tự nhiên, không cần thuộc từng chữ.
> Phần **Nhấn mạnh** là ý phải nói được dù quên lời. Phần **Nếu thầy hỏi** chuẩn bị sẵn câu trả lời ngắn.
> Gợi ý chia người: **Nhân** nói slide 1–11 (mở đầu, mục tiêu, SDN), **Hào** nói slide 12–20 (SD-WAN, Internet, việc còn lại, kế hoạch, khó khăn). Có thể đổi theo phần mỗi bạn trực tiếp làm.

---

## Slide 1 — Trang bìa (≈ 30 giây)

**Nói:**
> Em chào thầy. Nhóm em gồm hai thành viên là Trần Hữu Nhân và Nguyễn Nhật Hào. Hôm nay nhóm em xin báo cáo tiến độ tuần từ 28/09 đến 04/10/2026 của đề tài **"Xây dựng mạng Campus Network sử dụng SDN và SD-WAN"**.

---

## Slide 2 — Nội dung báo cáo (≈ 20 giây)

**Nói:**
> Bài báo cáo gồm năm phần: **mục tiêu**, **kết quả thực hiện trong tuần**, **công việc chưa hoàn thành**, **kế hoạch tuần tới** và cuối cùng là **những khó khăn** nhóm gặp phải.

---

## Slide 3 — Mục tiêu đề tài (≈ 1 phút)

**Nói:**
> Mục tiêu tổng quát là xây dựng mô hình mạng Campus **đa cơ sở** cho trường đại học trên **EVE-NG**, kết hợp **SDN** để điều khiển tập trung mạng LAN campus chính, và **SD-WAN** để kết nối các cơ sở qua hai đường truyền **Internet** và **MPLS**.
>
> Cụ thể gồm năm mục tiêu thành phần:
> 1. Kiến trúc phân cấp **Core – Distribution – Access**, dự phòng gateway bằng **VRRP**.
> 2. Quy hoạch VLAN, IP, DHCP cho **Site 100** là campus chính, ba chi nhánh **Cần Thơ, Đà Nẵng, Nha Trang**, và **Site 500** mới bổ sung tuần này.
> 3. Quản lý tập trung **6 switch Open vSwitch** bằng **Ryu** qua **OpenFlow 1.3**, và đánh giá theo **5 mục tiêu**: thời gian thêm VLAN, thời gian khôi phục, hiệu năng giữa các VLAN, tải thiết bị và quản lý chính sách tập trung.
> 4. Fabric **Cisco SD-WAN** với vManage, vSmart, vBond ở **Site 900**; mạng nền chạy **BGP** với hai nhà cung cấp.
> 5. Bảo mật và dịch vụ: tường lửa **FW-ASAv HA**, DMZ, Server Farm, DNS/DHCP, Syslog, và cho người dùng **ra Internet có kiểm soát**.

**Nhấn mạnh:** SDN lo **LAN campus chính**, SD-WAN lo **WAN giữa các cơ sở**.

**Nếu thầy hỏi:**
- *Vì sao dùng cả SDN lẫn SD-WAN?* → SDN tách control plane khỏi switch trong LAN để quản lý tập trung; SD-WAN làm điều tương tự ở tầng WAN, chọn đường theo chất lượng liên kết. Mỗi công nghệ giải quyết một phạm vi.

---

## Slide 4 — Topology tổng thể trên EVE-NG (≈ 1 phút)

**Nói:**
> Đây là topology tổng thể đang chạy trên EVE-NG.
> - Ở giữa phía dưới là **campus chính Site 100**: hai Core-SW chạy IOL, hai Distribution và bốn Access là **Open vSwitch** do Ryu điều khiển, cùng cặp tường lửa **FW-ASAv** chạy HA, vùng DMZ và Server Farm.
> - Bốn góc là các chi nhánh **Cần Thơ (200), Đà Nẵng (300), Nha Trang (400)** và **Site 500** mới thêm ở góc phải dưới.
> - Phía trên là **Site 900** chứa ba controller SD-WAN, và khối **Service Provider** gồm router Internet và MPLS chạy BGP.
> - Mỗi site có **hai vEdge**, một nối Internet, một nối MPLS — tức là hai "màu" đường truyền.

**Nhấn mạnh:** lab hiện có **70 node / 103 network**.

---

## Slide 5 — Mục tiêu của tuần (≈ 1 phút)

**Nói:**
> Tuần này nhóm em đặt năm mục tiêu:
> 1. Cho người dùng các site **ra Internet trực tiếp tại chỗ** (Direct Internet Access), có dự phòng và chính sách bảo mật.
> 2. **Nâng cấp Ryu controller lên phiên bản 2**: khôi phục nhanh khi mất liên kết, thêm VLAN động và chính sách tập trung.
> 3. Xây dựng **một giao diện quản trị duy nhất** là Campus SDN Console và **đo đủ 5 mục tiêu đánh giá SDN**.
> 4. Mở rộng topology với **Site 500**.
> 5. **Viết lại báo cáo Chương 1 đến 5** cho khớp cấu hình đã triển khai.

---

## Slide 6 — Tổng quan tiến độ theo hạng mục (≈ 1 phút)

**Nói:**
> Bảng này tổng hợp tiến độ toàn đề tài.
> - **Đã hoàn thành**: khảo sát và thiết kế; hạ tầng campus; ba chi nhánh 200/300/400; SD-WAN gồm controller, PKI, vEdge, BFD và chính sách vSmart; **SDN campus chính** với Ryu v2, Console và đã đo 5 mục tiêu; và **ra Internet** gồm NAT, DNS forwarder, dự phòng qua MPLS, ACL.
> - **Đang làm**: Site 500 và phần báo cáo, demo.

**Nhấn mạnh:** so với tuần trước, **SDN** và **Internet** đã chuyển sang **hoàn thành**.

---

## Slide 7 — SDN: Ryu controller v2 & Campus SDN Console (≈ 2 phút)

**Nói (cột trái):**
> Về controller phiên bản 2:
> - Controller **tự tính cây chuyển tiếp** trên đồ thị 13 liên kết bằng thuật toán **Dijkstra**, gốc là Core-SW1, dự phòng là Core-SW2. Liên kết ngoài cây bị chặn để không tạo vòng lặp.
> - Vì **EVE-NG không báo khi đầu xa của link bị đứt** — cổng vẫn hiện *up* — nên controller **chủ động gửi gói thăm dò** mỗi 0,5 giây trên từng liên kết để phát hiện mất link.
> - **VLAN 99** là VLAN quản trị dùng flow tĩnh có hướng, tách khỏi cây dữ liệu, nhờ đó hết tình trạng kẹt khi chuyển đổi dự phòng.
> - Sau khi cây đổi, controller phát **RARP** thay cho máy trạm để Core học lại MAC ngay.
> - Pipeline OpenFlow có **hai bảng**: bảng 0 kiểm soát và chính sách, bảng 1 chuyển tiếp.

**Nói (cột phải):**
> Campus SDN Console gom mọi thứ vào **một giao diện**: tổng quan, topology, khôi phục, lưu lượng, VLAN, chính sách, tải thiết bị và hiệu năng. Thêm VLAN hay luật chính sách chỉ cần gọi API, không phải sửa code. Ngoài ra có giám sát CPU Core qua SNMP, firewall bảo vệ REST API, và bộ test tự động.

**Nếu thầy hỏi:**
- *Vì sao không dùng STP?* → STP hội tụ chậm (vài chục giây) và không cho controller biết trạng thái; ở đây controller có cái nhìn toàn cục nên tự tính cây, chặn trước – mở sau để tránh vòng lặp.
- *RARP để làm gì?* → Core-SW1/2 là switch truyền thống, bảng MAC vẫn trỏ nhánh cũ; gửi RARP thay máy trạm qua nhánh mới giúp Core học lại ngay, nếu không dữ liệu mất 11–12 giây.

---

## Slide 8 — Giao diện Campus SDN Console (≈ 45 giây)

**Nói:**
> Đây là tab Tổng quan của Console, chụp ngày 04/10. Có thể thấy **6/6 switch OpenFlow** đang kết nối controller, **13/13 liên kết** đang sống, thời gian hội tụ gần nhất khoảng **8 ms**, biểu đồ băng thông theo thời gian và nhật ký sự kiện như switch kết nối hay cây thay đổi.

---

## Slide 9 — Đồ thị liên kết & cây dữ liệu (≈ 45 giây)

**Nói:**
> Tab Topology vẽ 13 liên kết giữa Core, Distribution và Access. **Đường xanh lá** là liên kết thuộc cây dữ liệu, gốc là Core-SW1; **đường xám** là liên kết dự phòng, vẫn sống nhưng bị chặn. Khi một liên kết chết, nó chuyển màu đỏ và controller tính lại cây, mở liên kết dự phòng thay thế. Từ giao diện này cũng có thể **mô phỏng cắt liên kết** để đo thời gian khôi phục.

---

## Slide 10 — Kết quả đo 5 mục tiêu đánh giá (≈ 2 phút)

**Nói:**
> Đây là kết quả đo ngày 04/10 cho năm mục tiêu:
> 1. **Thêm VLAN mới**: với SDN chỉ cần một lệnh API, mọi switch xác nhận trong **3,8 ms**. Làm thủ công trên Core truyền thống cần khoảng 18 lệnh CLI, khoảng **36 giây** mỗi thiết bị.
> 2. **Khôi phục khi mất link**: controller tính xong cây mới trong **dưới 16 ms**. Gián đoạn dữ liệu thực tế từ 0 đến 0,3 giây nếu cổng báo down, và 1,8 đến 3,4 giây nếu link đứt ngầm — phần lớn là thời gian chờ probe xác nhận link chết.
> 3. **Hiệu năng giữa các VLAN**: cùng VLAN RTT **1,57 ms**, khác VLAN qua Core **2,91 ms**, không mất gói, đo trên 36 cặp máy.
> 4. **Tải thiết bị**: tải điều khiển ổn định khoảng 93 packet-in mỗi giây, Ryu dùng khoảng 5% CPU, và **không tăng theo lưu lượng người dùng**.
> 5. **Chính sách tập trung**: luật chặn ICMP giữa VLAN 10 và 40 áp lên 4 switch Access trong **8 ms**, gỡ trong 5,2 ms, các luồng khác không bị ảnh hưởng.

**Nhấn mạnh:** số liệu đo trên lab thật, dữ liệu thô lưu trong `log/sdn-eval/`.

**Nếu thầy hỏi:**
- *Vì sao gián đoạn 1,8–3,4 s trong khi controller hội tụ 16 ms?* → 16 ms là thời gian từ lúc phát hiện đến khi mọi switch xác nhận flow mới; còn phát hiện link đứt ngầm phải chờ probe hết hạn (khoảng 2 giây) để tránh báo nhầm.
- *Vì sao tải điều khiển không phụ thuộc lưu lượng?* → Sau khi học MAC, flow được cài xuống switch, gói dữ liệu đi thẳng trên switch; controller chỉ nhận probe và gói chưa học.

---

## Slide 11 — Hiệu năng giữa các VLAN & tải thiết bị (≈ 1 phút)

**Nói:**
> Hình trên là **ma trận RTT** giữa các VLAN: hàng là VLAN nguồn, cột là VLAN đích. Đường chéo là cùng VLAN, đi thẳng qua OVS nên nhanh hơn; ngoài đường chéo là định tuyến qua Core-SW1.
> Hình dưới là **tải thiết bị**: băng thông qua Distribution, số packet-in gửi lên controller theo từng switch, lưu lượng uplink lên Core và CPU của controller.

---

## Slide 12 — SD-WAN: Giám sát tập trung trên vManage (≈ 1 phút)

**Nói:**
> Chuyển sang SD-WAN. Đây là trang Overview của **vManage**. Hệ thống có đủ **ba controller** vBond, vSmart, vManage. Có **8 WAN Edge reachable**; một thiết bị unreachable là **vEdge Site 500**, vì site này đang triển khai. Site Health cho thấy 4 site đều tốt, và Tunnel Health liệt kê các tunnel theo độ trễ.

**Nếu thầy hỏi:**
- *Vai trò 3 controller?* → vBond: xác thực và điều phối ban đầu; vSmart: control plane, phân phối route và chính sách qua OMP; vManage: quản trị, giám sát, GUI.

---

## Slide 13 — Thiết bị & tunnel trên vManage (≈ 1 phút)

**Nói:**
> Bên trái là danh sách thiết bị: 8 vEdge ở Site 100 đến 400 đều có kết nối tới vSmart, BFD lên đủ — **12/12** ở Site 100 và **8/8** ở mỗi chi nhánh.
> Bên phải là danh sách **72 tunnel SD-WAN** giữa các site trên cả hai màu **biz-internet** và **mpls**, kèm độ trễ, mất gói và jitter của từng tunnel; độ trễ cao nhất khoảng 65 ms.

**Nếu thầy hỏi:**
- *TLOC và "màu" là gì?* → TLOC là điểm cuối tunnel gồm System-IP, màu và kiểu đóng gói; màu là nhãn loại đường truyền (mpls, biz-internet).
- *BFD dùng để làm gì?* → Gửi hello liên tục trên từng tunnel để đo mất gói, độ trễ, jitter và phát hiện tunnel chết nhanh; là cơ sở để chọn đường theo SLA.

---

## Slide 14 — Cho các site ra Internet (DIA) (≈ 2 phút)

**Nói (cột trái):**
> Mục tiêu lớn thứ hai của tuần là cho người dùng ra Internet. Nhóm em làm theo sáu giai đoạn:
> - **Router Internet** nhận IP từ mạng LAN thật và NAT các dải WAN của lab ra ngoài.
> - Trên **vEdge** bật NAT ở cổng WAN, nên mỗi site **ra Internet ngay tại chỗ**, không phải vòng qua campus chính.
> - Tường lửa chi nhánh chọn đường: Internet chính qua vEdge2 đường biz-internet, có **theo dõi SLA** tới 9.9.9.9; khi đường này mất thì **tự chuyển sang MPLS** qua vEdge1.
> - DNS nội bộ chuyển tiếp ra 8.8.8.8 và 1.1.1.1; chỉ DNS server được hỏi ra ngoài.
> - Chính sách: VLAN quản trị 99 và Site 900 **không được ra Internet**; Server Farm và DMZ chỉ được dùng HTTP, HTTPS, NTP; log gửi về Syslog.

**Nói (cột phải):**
> Kết quả kiểm thử: máy ở ba chi nhánh nhận DHCP và ping được google.com; traceroute cho thấy hop đầu là vEdge tại chỗ; cắt đường biz-internet ở Cần Thơ thì sau khoảng 30 giây chuyển sang MPLS và tự quay về khi khôi phục; VLAN 99 và Site 900 bị chặn đúng thiết kế.

**Nếu thầy hỏi:**
- *Vì sao không cho chi nhánh ra Internet qua campus chính?* → Route NAT trên vEdge không quảng bá qua OMP, còn đặt route tĩnh thì default bị rò sang mọi site; dự phòng qua MPLS đơn giản và đúng mô hình DIA hơn.
- *Vì sao đích SLA là 9.9.9.9 mà không phải 8.8.8.8?* → Route /32 dành cho gói SLA sẽ kéo luôn lưu lượng người dùng tới 8.8.8.8 vào đường đang chết; dùng một đích riêng để tránh việc này.

---

## Slide 15 — Kiểm chứng tại chi nhánh Cần Thơ (≈ 1 phút)

**Nói:**
> Đây là output thật lấy trên thiết bị sáng 04/10.
> - Bên trái là tường lửa Cần Thơ: hai track SLA đều **Up**, default route đi qua vEdge2 ở cổng `outside2`, ping 8.8.8.8 **5/5**, traceroute ra thẳng đường biz-internet tại chỗ.
> - Bên phải là vEdge2 Cần Thơ: **8 phiên BFD up** tới Site 100, 300, 400 trên cả hai màu, và phiên OMP với vSmart đang up.

---

## Slide 16 — Mở rộng topology & tài liệu (≈ 45 giây)

**Nói:**
> Về topology, nhóm em bổ sung **Site 500** gồm switch, hai máy trạm và một vEdge nối cả Internet lẫn MPLS; phía nhà cung cấp đã cấu hình địa chỉ và BGP AS 65040 cho site này. Lab hiện có 70 node.
> Về tài liệu, nhóm em viết lại báo cáo Chương 1 đến 5 cho khớp cấu hình thực tế, bổ sung mục thiết kế về controller v2 và kết quả đánh giá, cùng tài liệu hướng dẫn sử dụng Console.

---

## Slide 17 — Vấn đề còn tồn tại (≈ 1 phút 30 giây)

**Nói:**
> Các vấn đề chưa xử lý xong:
> - **Site 500**: vEdge Site 500 vẫn mang cấu hình cũ, chưa đặt system-ip, site-id và BGP; switch và máy trạm chưa cấu hình.
> - **VLAN 99 giữa Site 100 và chi nhánh không thông**: gói trả về đi ra cổng management của tường lửa — định tuyến bất đối xứng.
> - **Điểm lỗi đơn của VLAN 99**: kênh điều khiển SDN phụ thuộc vào một liên kết Dist-SW2 – Core-SW1.
> - SNMP Core-SW2 chưa đọc được; probe bị nhiễu khoảng 3 giây khi Dist-SW1 khởi động.
> - ONOS vẫn chạy song song với Ryu, chưa quyết định giữ hay gỡ.
> - Chưa thử máy trạm Site 100 ra Internet và chưa thử cắt đường ở Đà Nẵng, Nha Trang.

**Nhấn mạnh:** mỗi vấn đề đều đã **xác định được nguyên nhân** và có hướng xử lý ở slide sau.

**Nếu thầy hỏi:**
- *Điểm lỗi đơn ảnh hưởng gì?* → Nếu liên kết đó đứt, Dist-SW2 và 4 Access mất kết nối controller; dữ liệu vẫn chạy bằng flow cũ nhưng không đổi được cây cho tới khi kênh điều khiển phục hồi.

---

## Slide 18 — Nhiệm vụ tuần tới 05/10 – 11/10 (≈ 1 phút 30 giây)

**Nói (cột trái — Kỹ thuật):**
> 1. Cấu hình **Site 500**: vEdge với system-ip, site-id 500, hai màu đường truyền, BGP; switch và máy trạm; đưa lên vManage và kiểm tra BFD, OMP.
> 2. Sửa định tuyến bất đối xứng VLAN 99 trên tường lửa.
> 3. Thêm đường quản trị thứ hai cho VLAN 99 để bỏ điểm lỗi đơn.
> 4. Kiểm thử máy trạm Site 100 ra Internet qua OVS; cắt đường biz-internet ở Đà Nẵng và Nha Trang.
> 5. Quyết định giữ hay gỡ ONOS.

**Nói (cột phải — Báo cáo & demo):**
> 6. Đưa số liệu 5 mục tiêu SDN và ma trận kiểm thử Internet vào Chương 4, cập nhật kết luận Chương 5.
> 7. Thay ảnh topology mới trong báo cáo.
> 8. Soạn kịch bản demo: máy trạm nhận DHCP, thêm VLAN và chính sách trên Console, cắt link SDN, cắt một màu WAN, rồi ra Internet.

---

## Slide 19 — Khó khăn gặp phải trong tuần (≈ 1 phút 30 giây)

**Nói:**
> Nhóm em gặp năm khó khăn chính:
> 1. **EVE-NG không báo mất link đầu xa**: cổng vẫn up khi link bị cắt, nên phải tự thăm dò bằng probe và chấp nhận gián đoạn 1,8 đến 3,4 giây.
> 2. **Mất kênh điều khiển dễ bị hiểu nhầm là đứt link**: khi nhiều switch cùng im lặng, controller từng chặn cây sai. Nhóm em sửa bằng cách coi đó là mất kênh điều khiển và giữ nguyên cây; các lần cắt thử tự hết hạn để switch tự phục hồi.
> 3. **Vòng lặp default route**: vEdge quảng bá ngược default học từ MPLS lên router Internet làm cả lab mất Internet; sửa bằng prefix-list lọc chiều vào.
> 4. **Hạn chế thiết bị ảo**: ASAv chưa có license nên giới hạn 100 kết nối và khoảng 100 Kbps; Core IOL bị treo khi xoá SVI đang là VRRP master.
> 5. **Tài nguyên máy chủ EVE-NG**: tiến trình vEdge Site 500 bị treo làm máy chủ quá tải, phải khởi động lại router MPLS bị tắt nhầm.

**Nếu thầy hỏi:**
- *Nhóm chẩn đoán lỗi thế nào?* → Đi theo từng lớp: link → L2 → L3 → dịch vụ → ứng dụng; dừng ở lớp đầu tiên sai và có bằng chứng (`show`, bắt gói) cho mỗi kết luận.

---

## Slide 20 — Kết thúc (≈ 15 giây)

**Nói:**
> Trên đây là toàn bộ báo cáo tiến độ tuần này của nhóm em. Em xin cảm ơn thầy đã lắng nghe, và nhóm em rất mong nhận được góp ý của thầy ạ.

---

## Phụ lục A — Thuật ngữ nhanh

| Thuật ngữ | Giải thích một câu |
|---|---|
| SDN | Tách phần điều khiển (controller) khỏi phần chuyển tiếp (switch), quản lý mạng tập trung bằng phần mềm. |
| OpenFlow 1.3 | Giao thức controller dùng để cài flow (luật khớp + hành động) xuống switch. |
| OVS | Open vSwitch — switch ảo hỗ trợ OpenFlow. |
| Ryu | Controller SDN viết bằng Python. |
| Probe | Gói thăm dò controller tự gửi trên từng liên kết để biết link còn sống. |
| Packet-in | Gói switch gửi lên controller khi chưa có flow phù hợp. |
| SD-WAN | WAN định nghĩa bằng phần mềm: overlay trên nhiều đường truyền, chọn đường theo chính sách/SLA. |
| vManage / vSmart / vBond | Quản trị / control plane (OMP) / điều phối & xác thực. |
| TLOC / Color | Điểm cuối tunnel (System-IP + màu + đóng gói) / nhãn loại đường truyền. |
| BFD | Kiểm tra sống và đo chất lượng từng tunnel. |
| DIA | Direct Internet Access — site ra Internet ngay tại chỗ, không vòng qua campus chính. |
| SLA monitor / track | Tường lửa ping định kỳ một đích; mất phản hồi thì gỡ route chính, chuyển sang route dự phòng. |
| VRRP | Gateway ảo dự phòng giữa hai Core. |

## Phụ lục B — Lưu ý trước khi báo cáo

- Ảnh Console và vManage chụp sáng **04/10/2026**; nếu demo trực tiếp, trạng thái có thể khác ảnh.
- Trên vManage, **vEdge Site 500 hiện unreachable** — nói rõ là đang triển khai, không phải lỗi.
- Ô "92 Tunnels" trên Overview tính theo cửa sổ 24 giờ (nhiều khả năng gồm cả tunnel từng lên rồi xuống, ví dụ khi thử cắt đường); danh sách hiện tại có **72 tunnel** (slide 13). Nếu thầy hỏi, nên mở vManage kiểm lại trước khi khẳng định.
