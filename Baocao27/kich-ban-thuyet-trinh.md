# Kịch bản thuyết trình — Báo cáo tiến độ hằng tuần

**Đề tài:** Xây dựng mạng Campus Network sử dụng SDN và SD-WAN
**Nhóm:** Trần Hữu Nhân (52300235) — Nguyễn Nhật Hào (52300198)
**Slide:** `report.pdf` (10 slide) · **Thời lượng dự kiến:** 10–12 phút + hỏi đáp

> Cách dùng: phần **Nói** là lời thoại gợi ý, đọc tự nhiên, không cần thuộc từng chữ.
> Phần **Nhấn mạnh** là ý phải nói được dù quên lời. Phần **Nếu thầy/cô hỏi** chuẩn bị sẵn câu trả lời ngắn.
> Gợi ý chia người: **Nhân** nói slide 1–6 (mở đầu, mục tiêu, SD-WAN), **Hào** nói slide 7–10 (SDN, việc còn lại, khó khăn, kết thúc). Có thể đổi theo phần mỗi bạn trực tiếp làm.

---

## Slide 1 — Trang bìa (≈ 30 giây)

**Nói:**
> Em chào thầy/cô. Nhóm em gồm hai thành viên là Trần Hữu Nhân và Nguyễn Nhật Hào. Hôm nay nhóm em xin báo cáo tiến độ hằng tuần của đề tài **"Xây dựng mạng Campus Network sử dụng SDN và SD-WAN"**, thuộc môn Dự án Công nghệ Thông tin.

**Nhấn mạnh:** tên đề tài, hai thành viên, đây là báo cáo **tiến độ tuần**.

---

## Slide 2 — Nội dung báo cáo (≈ 20 giây)

**Nói:**
> Bài báo cáo gồm bốn phần: thứ nhất là **mục tiêu** của đề tài và của tuần này; thứ hai là **tiến độ đã thực hiện**; thứ ba là **các công việc chưa hoàn thành** cùng kế hoạch tiếp theo; và cuối cùng là **những khó khăn** nhóm gặp phải.

---

## Slide 3 — Mục tiêu đề tài (≈ 1 phút 30 giây)

**Nói:**
> Mục tiêu tổng quát của đề tài là xây dựng một mô hình mạng Campus **đa cơ sở** cho trường đại học trên nền tảng giả lập **EVE-NG**. Mô hình kết hợp hai công nghệ:
> - **SDN** để điều khiển tập trung mạng LAN của campus chính, và
> - **SD-WAN** để kết nối thông minh giữa các cơ sở qua hai đường truyền là **Internet** và **MPLS**.
>
> Cụ thể, nhóm em đặt ra năm mục tiêu thành phần:
> 1. Thiết kế kiến trúc phân cấp ba lớp **Core – Distribution – Access**, có dự phòng gateway bằng **VRRP** và định tuyến **OSPF Area 0**.
> 2. Quy hoạch VLAN, địa chỉ IP và DHCP cho **Site 100** là campus chính và ba chi nhánh **Cần Thơ (Site 200)**, **Đà Nẵng (Site 300)**, **Nha Trang (Site 400)**.
> 3. Quản lý tập trung các switch **Open vSwitch** bằng **Ryu Controller** thông qua giao thức **OpenFlow 1.3**.
> 4. Dựng hệ thống **Cisco SD-WAN** gồm ba controller vManage, vSmart, vBond đặt ở **Site 900**, cùng **8 router vEdge**; mạng nền (underlay) chạy **BGP** với hai nhà cung cấp: Internet AS 64511 và MPLS AS 64512.
> 5. Bảo mật và dịch vụ: tường lửa **FW-ASAv chạy HA**, vùng **DMZ**, **Server Farm**, **Syslog** và giám sát **NOC**.

**Nhấn mạnh:** SDN lo **LAN campus chính**, SD-WAN lo **WAN giữa các cơ sở** — hai công nghệ bổ trợ nhau.

**Nếu thầy/cô hỏi:**
- *Vì sao dùng cả SDN lẫn SD-WAN?* → SDN tách control plane khỏi switch trong LAN để quản lý tập trung; SD-WAN làm việc tương tự nhưng ở tầng WAN, chọn đường theo chất lượng liên kết (Internet/MPLS). Mỗi công nghệ giải quyết một phạm vi khác nhau.
- *VRRP để làm gì?* → Hai Core-SW chia sẻ một gateway ảo; một Core hỏng thì Core còn lại tiếp quản, máy trạm không phải đổi gateway.

---

## Slide 4 — Mục tiêu của tuần (≈ 1 phút)

**Nói:**
> Trong tuần này nhóm em đặt ra năm mục tiêu:
> 1. **Ổn định fabric SD-WAN**: đủ 8 trên 8 vEdge ở trạng thái *reachable*, các tunnel BFD full-mesh lên đủ trên cả **hai màu** đường truyền.
> 2. **Khắc phục đường dữ liệu SDN** trong campus để gói **DHCP** đi xuyên qua được các switch OVS.
> 3. **Đưa giao diện quản trị vManage ra mạng LAN thật**, để có thể thao tác từ laptop thay vì chỉ trong lab.
> 4. **Phân tích và giải thích** các số liệu tunnel và *Transport Health* hiển thị trên vManage.
> 5. **Đồng bộ cấu hình lab** theo chiều host 1 sang repo rồi sang host 2, đồng thời cập nhật tài liệu.

**Nhấn mạnh:** "hai màu" = hai loại đường truyền (màu TLOC) — Internet và MPLS.

---

## Slide 5 — Tổng quan tiến độ theo hạng mục (≈ 1 phút 30 giây)

**Nói:**
> Đây là bảng tổng quan tiến độ theo từng giai đoạn.
> - Bốn hạng mục đã **hoàn thành**: khảo sát và thiết kế (lý thuyết SDN/SD-WAN, topology, bảng IP/VLAN/ASN); hạ tầng campus L2/L3 (Core/Distribution/Access, VRRP, OSPF, tường lửa ASAv HA và ASDM); ba chi nhánh 200/300/400 (Brand-FW, DHCP, SwitchBrand, VPC); và SD-WAN (controller, PKI, 8 vEdge, BGP underlay).
> - Hai hạng mục **đang làm**: SDN campus chính với Ryu và 6 switch OVS, ứng dụng L2 và NOC Dashboard; và DHCP campus chính trên Windows Server 2012 R2 với 4 scope và relay trên Core.
> - Hạng mục **chưa làm** là dịch vụ và kiểm thử: Web/Mail, ma trận test và các kịch bản failover.

**Nhấn mạnh:** phần nền tảng (thiết kế, hạ tầng, chi nhánh, SD-WAN) đã xong; trọng tâm hiện tại là **SDN + DHCP campus chính**, sau đó là **kiểm thử**.

**Nếu thầy/cô hỏi:**
- *PKI trong SD-WAN là gì?* → Hạ tầng chứng chỉ: mỗi thiết bị có chứng chỉ do CA gốc ký; controller và vEdge xác thực nhau bằng chứng chỉ trước khi lập kết nối điều khiển (DTLS/TLS).

---

## Slide 6 — Tiến độ SD-WAN (≈ 2 phút)

**Nói (cột trái — Đã hoàn thành):**
> Về SD-WAN, nhóm em đã hoàn thành:
> - Dựng **3 controller** vManage, vSmart, vBond cùng **CA gốc**, và chuẩn hoá quy trình tạo CSR, ký chứng chỉ, cài *root-cert-chain* cho thiết bị.
> - Khai báo **whitelist đủ 8 serial vEdge trên cả 3 controller** — vEdge nào không có trong danh sách này sẽ bị từ chối.
> - Kết quả: **8/8 vEdge reachable**, có **10 TLOC**, tạo ra **36 tunnel** duy nhất, tương ứng **72 phiên BFD** (mỗi tunnel được đếm ở hai đầu).
> - Mạng nền **BGP**: phiên eBGP giữa hai nhà cung cấp AS 64511 và 64512 đã *Established*, và các phiên CE–PE trên cả 8 vEdge đều lên.

**Nói (cột phải — Sự cố đã xử lý):**
> Trong tuần nhóm em xử lý bốn vấn đề:
> 1. vEdge ở Site 100 chỉ kết nối được **1 trên 3 vSmart**. Nguyên nhân là route tới controller chỉ có một ngả; nhóm em thêm route /24 tới controller qua đường **biz-internet** để có ECMP, sau đó vEdge lên đủ **3/3** kết nối điều khiển.
> 2. vEdge Site 100 **rơi khỏi fabric sau khi reboot** controller: do whitelist *valid-vedges* bị mất, nhóm em đã bổ sung lại.
> 3. Nối **Switch61 ra Cloud** để đưa vManage ra mạng LAN thật, nhờ đó mở được GUI vManage từ laptop.
> 4. Viết tài liệu giải thích ý nghĩa **Tunnel** và **Transport Health** trên vManage.

**Nhấn mạnh:** fabric đã **đủ 8/8 vEdge**, và nhóm hiểu **nguyên nhân gốc** của từng sự cố chứ không chỉ sửa tạm.

**Nếu thầy/cô hỏi:**
- *TLOC là gì?* → Transport Locator = bộ (System-IP, màu, kiểu đóng gói) — điểm cuối của tunnel trên mỗi đường truyền của vEdge. vEdge có hai đường thì có hai TLOC.
- *BFD dùng để làm gì?* → Gửi gói hello liên tục trên từng tunnel để đo mất gói, độ trễ, jitter và phát hiện tunnel chết nhanh; số liệu này là cơ sở cho Transport Health và chọn đường theo SLA.
- *Vai trò 3 controller?* → vBond: điều phối, xác thực ban đầu (orchestrator); vSmart: control plane, phân phối route và chính sách qua OMP; vManage: quản trị, giám sát, GUI.
- *"Màu" (color) là gì?* → Nhãn đánh dấu loại đường truyền (vd. mpls, biz-internet); vEdge dùng màu để quyết định tunnel nào được lập và dùng IP public hay private.

---

## Slide 7 — Tiến độ SDN campus chính & hạ tầng (≈ 2 phút)

**Nói (cột trái — SDN):**
> Về SDN ở campus chính:
> - **Ryu** chạy trên máy SDN_CONTROLLER, địa chỉ **10.1.99.10**, cổng OpenFlow **6653** và REST **8080**. Các switch được điều khiển qua **VLAN 99** là VLAN quản trị.
> - Nhóm em sửa ứng dụng `campus_switch_13.py`: thay đổi hành vi **table-miss** — tức là khi gói tin không khớp flow nào — từ gửi về **CONTROLLER** sang **NORMAL**, và cho ứng dụng tự cài lại flow này mỗi khi switch kết nối lại.
> - Kết quả là gói **DHCP Discover đã đi xuyên được campus**, và DHCP relay trên hai Core-SW đã hoạt động.
> - Nhóm em cũng triển khai ứng dụng giám sát **NOC** `campus_noc_monitor.py` gồm **Dashboard** và **REST API**.

**Nói (cột phải — Hạ tầng & vận hành):**
> Về hạ tầng và vận hành lab:
> - DHCP-Server chạy **Windows Server 2012 R2** với **4 scope** cho VLAN 10, 20, 30, 40, đều ở trạng thái Active.
> - OVS và Ryu **tự khôi phục khi khởi động** nhờ các dịch vụ systemd.
> - **Syslog** (Kiwi) nhận log từ Core, Server Farm và cặp tường lửa ASAv HA.
> - Nhóm em chuẩn hoá quy trình **đồng bộ một chiều**: host 1 là nguồn chuẩn, đồng bộ sang repo rồi sang host 2; cấu hình khởi động được nhúng trực tiếp trong file `.unl` của EVE-NG.

**Nhấn mạnh:** vấn đề DHCP là do **hành vi OpenFlow** (table-miss), không phải do DHCP-Server.

**Nếu thầy/cô hỏi:**
- *Table-miss là gì, vì sao làm rơi DHCP?* → Là flow ưu tiên thấp nhất, áp dụng khi gói không khớp flow nào. Nếu gửi mọi gói về controller thì broadcast DHCP phụ thuộc hoàn toàn vào việc controller xử lý và đẩy ra đúng cổng/VLAN; xử lý sai là gói bị rơi. Chuyển sang NORMAL cho OVS tự chuyển tiếp như switch L2 thông thường.
- *Vì sao điều khiển qua VLAN 99 mà không dùng mạng riêng?* → Lab không có mạng quản trị out-of-band riêng; VLAN 99 là VLAN quản trị chung (in-band) cho controller và thiết bị.
- *DHCP relay là gì?* → Core-SW nhận broadcast DHCP của máy trạm ở VLAN người dùng rồi chuyển tiếp dạng unicast tới DHCP-Server ở Server Farm (VLAN 90), ghi giaddr để server chọn đúng scope.

---

## Slide 8 — Công việc còn lại (≈ 1 phút 30 giây)

**Nói (cột trái — Đang dở):**
> Các việc còn đang dở:
> - DHCP-Server đã nhận được Discover nhưng **chưa trả OFFER**. Hướng xử lý là kiểm tra dịch vụ DHCP, scope, trường **giaddr** của relay, và bắt gói **hai chiều** để xem OFFER mất ở đâu.
> - **Access-SW3 và SW4** chưa kết nối ổn định với Ryu.
> - NOC Dashboard vẫn hiển thị tổng Rx/Tx bằng 0 vì chưa có lưu lượng thật đi qua datapath của OVS.
> - Cần đưa bản vá ứng dụng Ryu về repo trong thư mục `configs/`.

**Nói (cột phải — Kế hoạch tiếp theo):**
> Kế hoạch sắp tới:
> - **Ping liên site** từ Site 100 sang 200/300/400 qua tunnel SD-WAN, kiểm tra bảng route OMP và BGP.
> - Triển khai dịch vụ **Web/Mail**, truy cập được từ nhiều site; hoàn thiện kịch bản demo **ASDM**.
> - Xây dựng **ma trận kiểm thử**: DHCP từng site, failover tường lửa HA, cắt một màu đường WAN, và mất controller SDN.
> - Hoàn thiện báo cáo, slide và kịch bản demo bảo vệ, dự kiến **cuối tháng 11/2026**.

**Nhấn mạnh:** mỗi việc dở đều **có hướng xử lý cụ thể**; kế hoạch hướng tới **kiểm thử và demo**.

---

## Slide 9 — Khó khăn gặp phải (≈ 1 phút 30 giây)

**Nói:**
> Trong quá trình thực hiện nhóm em gặp sáu khó khăn chính:
> 1. **Tài nguyên lab lớn**: hơn 50 node gồm IOL, ASAv, vEdge, Windows Server trên một EVE-NG, nên khởi động chậm, có node bấm start nhưng không chạy, ví dụ SDN_CONTROLLER.
> 2. **Trạng thái runtime bị mất sau reboot**: whitelist valid-vedges trên controller phải bổ sung lại, nếu không vEdge rơi khỏi fabric.
> 3. **Lỗi SD-WAN khó chẩn đoán**: thiếu root-cert-chain, cấu hình sai `color` trên tunnel-interface, hay route tới controller chỉ có một ngả đều dẫn tới cùng một biểu hiện là tunnel down và health báo đỏ.
> 4. **Hành vi OpenFlow**: table-miss gửi về controller làm rơi broadcast DHCP; ngoài ra Ryu bản cũ chạy Python 3.6 có API khác với tài liệu hiện hành.
> 5. **Đồng bộ nhiều host**: cấu hình nhúng trong file `.unl` dễ bị ghi đè khi export/import hoặc khi merge git, nên nhóm phải chuẩn hoá quy trình đồng bộ một chiều.
> 6. **Truy cập từ xa**: GUI vManage nằm bên trong lab, phải thêm route và dùng SSH tunnel mới mở được từ laptop.

**Nhấn mạnh:** với mỗi khó khăn, nhóm đã có **cách khắc phục** (đã trình bày ở slide 6–7).

**Nếu thầy/cô hỏi:**
- *Nhóm chẩn đoán lỗi thế nào?* → Đi theo từng lớp: vật lý/link → L2 (VLAN, trunk) → L3 (route, BGP) → dịch vụ (DHCP, control connection) → ứng dụng; dừng ở lớp đầu tiên sai và có bằng chứng (`show`, bắt gói) cho mỗi kết luận.

---

## Slide 10 — Kết thúc (≈ 15 giây)

**Nói:**
> Trên đây là toàn bộ báo cáo tiến độ tuần này của nhóm em. Em xin cảm ơn thầy/cô đã lắng nghe, và nhóm em rất mong nhận được góp ý của thầy/cô ạ.

---

## Phụ lục A — Thuật ngữ nhanh

| Thuật ngữ | Giải thích một câu |
|---|---|
| SDN | Tách phần điều khiển (controller) khỏi phần chuyển tiếp (switch), quản lý mạng tập trung bằng phần mềm. |
| OpenFlow 1.3 | Giao thức controller dùng để cài flow (luật khớp + hành động) xuống switch. |
| OVS | Open vSwitch — switch ảo hỗ trợ OpenFlow. |
| Ryu | Controller SDN viết bằng Python. |
| SD-WAN | WAN định nghĩa bằng phần mềm: overlay trên nhiều đường truyền, chọn đường theo chính sách/SLA. |
| vManage / vSmart / vBond | Quản trị / control plane (OMP) / điều phối & xác thực. |
| vEdge | Router biên SD-WAN tại mỗi site. |
| TLOC | Điểm cuối tunnel = System-IP + màu + đóng gói. |
| Color | Nhãn loại đường truyền (mpls, biz-internet…). |
| BFD | Kiểm tra sống/đo chất lượng từng tunnel. |
| OMP | Giao thức vSmart dùng để phân phối route/TLOC/chính sách. |
| VRRP | Gateway ảo dự phòng giữa hai Core. |
| DHCP relay / giaddr | Chuyển tiếp DHCP qua router; giaddr cho server biết cấp IP từ scope nào. |

## Phụ lục B — Lưu ý trước khi báo cáo (đối chiếu với trạng thái thực tế của dự án)

Một số nội dung trên slide có vẻ được giữ lại từ các tuần trước và **không còn khớp** với ghi nhận mới nhất của dự án. Nên xem lại hoặc chuẩn bị câu trả lời nếu giảng viên hỏi:

- **DHCP campus chính (slide 5, 7, 8):** slide ghi "chưa trả OFFER", nhưng ghi nhận ngày **15/09** và **20/09** cho thấy DHCP campus đã chạy end-to-end (8/8 VPC nhận IP đúng scope, DORA đủ). Phần còn dở thực tế là **DHCP khi failover** (tắt Dist-SW1 thì máy trạm không xin lại được IP) và lỗi mất kết nối khi failback.
- **Table-miss (slide 7):** trạng thái đã kiểm tra ngày 21/09 là table-miss `priority=0 → CONTROLLER` và ứng dụng Ryu tự xử lý broadcast/VLAN. Nếu nói "chuyển sang NORMAL", nên nắm rõ đó là cách sửa ở giai đoạn nào.
- **Access-SW3/SW4 (slide 8):** từ **20/09** cả 6/6 OVS đã kết nối Ryu ổn định (nguyên nhân storm là in-band control của OVS, đã tắt).
- **SD-WAN (slide 6):** từ **23/09** overlay đã mang dữ liệu người dùng (service VPN 1), BFD 56/56, đã áp SLA/AAR/data policy — có thể bổ sung như điểm mới của tuần.
- **ONOS (21/09)** chạy song song Ryu làm GUI giám sát — chưa có trên slide, có thể nhắc nếu được hỏi về giao diện SDN.
- **Ngày trên slide** là 26/09/2026 (dùng `\today`, sẽ đổi theo ngày biên dịch lại).
