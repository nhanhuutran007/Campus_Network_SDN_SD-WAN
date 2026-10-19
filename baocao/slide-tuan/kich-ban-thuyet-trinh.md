# Kịch bản thuyết trình — Báo cáo tiến độ tuần 05/10 – 11/10/2026

**Đề tài:** Xây dựng mạng Campus Network sử dụng SDN và SD-WAN
**Nhóm:** Trần Hữu Nhân (52300235) — Nguyễn Nhật Hào (52300198)
**Slide:** `report.pdf` (18 slide) · **Thời lượng dự kiến:** 15–17 phút + hỏi đáp

> Cách dùng: phần **Nói** là lời thoại gợi ý, đọc tự nhiên, không cần thuộc từng chữ.
> Phần **Nhấn mạnh** là ý phải nói được dù quên lời. Phần **Nếu thầy hỏi** chuẩn bị sẵn câu trả lời ngắn.
> Gợi ý chia người: **Nhân** nói slide 1–10 (mở đầu, mục tiêu, SDN), **Hào** nói slide 11–18 (SD-WAN, Site 900, cảnh báo, tài liệu, việc còn lại, kế hoạch, khó khăn). Có thể đổi theo phần mỗi bạn trực tiếp làm.

---

## Slide 1 — Trang bìa (≈ 30 giây)

**Nói:**
> Em chào thầy. Nhóm em gồm hai thành viên là Trần Hữu Nhân và Nguyễn Nhật Hào. Hôm nay nhóm em xin báo cáo tiến độ tuần từ 05/10 đến 11/10/2026 của đề tài **"Xây dựng mạng Campus Network sử dụng SDN và SD-WAN"**.

---

## Slide 2 — Nội dung báo cáo (≈ 20 giây)

**Nói:**
> Bài báo cáo gồm năm phần: **mục tiêu**, **kết quả thực hiện trong tuần**, **công việc chưa hoàn thành**, **kế hoạch tuần tới** và **những khó khăn** nhóm gặp phải.

---

## Slide 3 — Mục tiêu đề tài (≈ 45 giây)

**Nói:**
> Mục tiêu tổng quát vẫn là mô hình mạng Campus **đa cơ sở** trên **EVE-NG**: **SDN** điều khiển tập trung mạng LAN campus chính, **SD-WAN** kết nối các cơ sở qua **Internet** và **MPLS**. So với tuần trước, nhóm nhấn mạnh thêm hai yêu cầu: mạng SDN phải **tự phục hồi** khi mất liên kết, và hệ thống SD-WAN phải **tự cảnh báo** khi có sự cố.

---

## Slide 4 — Topology tổng thể (≈ 30 giây)

**Nói:**
> Topology không đổi so với tuần trước: **70 node, 103 network**, gồm Campus chính, ba chi nhánh, Site 500 mở rộng, Site 900 đặt controller SD-WAN và hai nhà cung cấp chạy BGP.

---

## Slide 5 — Mục tiêu của tuần và mức độ hoàn thành (≈ 1 phút 30 giây)

**Nói:**
> Tuần trước nhóm đặt ra bảy nhiệm vụ. Bốn nhiệm vụ đã **hoàn thành**: bỏ điểm lỗi đơn của kênh quản trị VLAN 99, sửa định tuyến bất đối xứng VLAN 99 trên tường lửa, quyết định về ONOS — nhóm đã **tắt** ONOS — và cập nhật báo cáo Chương 4, 5.
> Hai việc **chưa làm**: cấu hình Site 500 và hai phép thử Internet còn thiếu. Kịch bản demo đang soạn.
> Ngoài kế hoạch, tuần này phát sinh thêm: kiểm thử khởi động nguội và cắt link thật, hai tab mới trên Console, sửa vEdge1 Site 300, cho Site 900 ra Internet có kiểm soát và làm cảnh báo email.

**Nhấn mạnh:** Site 500 chậm vì nhóm ưu tiên làm SDN tự phục hồi cho chắc trước.

---

## Slide 6 — Tổng quan tiến độ theo hạng mục (≈ 45 giây)

**Nói:**
> Hầu hết hạng mục đã hoàn thành. Hai hạng mục mới chuyển sang hoàn thành tuần này là **tự phục hồi SDN S1–S6** và **giám sát, cảnh báo**. Còn đang làm là Site 500 và phần báo cáo, demo.

---

## Slide 7 — SDN: kiểm thử khởi động nguội & cắt link thật (≈ 2 phút)

**Nói:**
> Tuần trước nhóm mới thử bằng mô phỏng. Tuần này nhóm cắt **thật** — hạ giao diện ảo trên máy chủ EVE-NG, giống như rút dây — và bật lại cả campus cùng lúc.
> Hai ca lộ lỗi nặng: cắt kép A4-D1 + D2-C1 thì mạng **kẹt** ở 9/13 link, Dist-SW2 mất controller **vĩnh viễn**; tắt hẳn Dist-SW2 thì **bốn VLAN mất 100% khoảng 3,5 phút**.
> Nguyên nhân chung: controller coi switch **mất kết nối** là switch **chết**, trong khi OVS ở chế độ `secure` vẫn chạy bằng flow cũ. Nhóm sửa bốn chỗ như trên slide; sau sửa, tắt hẳn Dist-SW2 chỉ mất **0–5 gói**.

**Nếu thầy hỏi "đóng băng" là gì:** Access mất kết nối controller vẫn được giữ trong cây trên đúng link cũ, controller không chặn cổng xuống nó nữa.

---

## Slide 8 — SDN: tìm nguyên nhân controller bị khựng (≈ 1 phút 30 giây)

**Nói:**
> Có hiện tượng controller **khựng** theo cụm, mỗi 5–15 phút một lần, mỗi lần tới 9 giây. Nhóm ghi CPU từng tiến trình mỗi nửa giây và thấy trong cụm khựng, máy ảo 2 vCPU **không còn CPU rảnh**, tiến trình **java của ONOS** chiếm hơn một vCPU, Ryu bị đói CPU.
> Vì ONOS chỉ dùng để xem topology mà Console đã làm được, nhóm **tắt ONOS** và ưu tiên CPU cho Ryu. RAM của controller giảm từ 1,3 GB còn 179 MB.

**Nhấn mạnh:** quyết định về ONOS dựa trên số đo, không phải cảm tính.

---

## Slide 9 — SDN: kênh quản trị VLAN 99 không phụ thuộc STP (≈ 2 phút)

**Nói:**
> Hai kịch bản S4, S5 vẫn không đạt. Nhóm theo dõi STP trên Core-SW1 trong lúc cắt link và thấy: khung VLAN 99 đi **vòng qua khối OVS** rồi quay về Core, nên Core **nghe chính BPDU của nó**. Khi khôi phục, cổng Et1/2 rơi vào trạng thái **Dispute** của RSTP khoảng 8 giây — cả 6 OVS mất controller.
> Cách sửa là thiết kế lại luật flow cho VLAN 99: khung từ cổng Core **không bao giờ** đi ra cổng Core khác. Khi đó hai cổng của Core đều forwarding, STP chỉ còn là lưới an toàn; mỗi switch có **nhiều đường quản trị cùng lúc**. Nhóm **không phải sửa Core-SW1** hay script OVS, chỉ đổi flow do controller cài.

**Nếu thầy hỏi vì sao không cho Core-SW2 vào VLAN 99:** đã thử, hai router cùng VLAN với OVS flood tĩnh gây bão khoảng 40.000 gói/giây.

---

## Slide 10 — SDN: kết quả 6 kịch bản tự phục hồi (≈ 1 phút 30 giây)

**Nói:**
> Tab **Kịch bản** trên Console chạy tự động sáu kịch bản cắt link và tự kết luận đạt hay không. Sau khi sửa, **cả 6/6 đều đạt**: gián đoạn khi cắt tối đa 3,5 giây, khi khôi phục gần như bằng 0, không switch nào mất controller. S4 và S5 trước đây không đạt nay đạt. Cắt thật cũng đạt cả ba ca.
> Tab **Sức khoẻ** mới cho thấy trạng thái kênh điều khiển từng switch và vai trò STP của Core-SW1 đọc qua SNMP.

**Nhấn mạnh:** gián đoạn khi cắt chủ yếu là **thời gian phát hiện** (thăm dò mỗi 0,5–1 giây); controller hội tụ chỉ vài mili giây.

---

## Slide 11 — SD-WAN: hai sự cố đã sửa (≈ 1 phút 30 giây)

**Nói:**
> Thứ nhất, VLAN 99 Campus chính không ping được chi nhánh. Lý do là cổng Management của tường lửa nằm thẳng trong mạng 10.1.99.0/24 nên gói trả về đi ra cổng management, tường lửa huỷ vì không khớp phiên. Nhóm sửa theo chuẩn **quản trị ngoài băng**: đặt `management-only` và thêm tuyến 10.1.99.0/24 qua Core-SW1. Kết quả thông tới cả ba chi nhánh, ASDM vẫn chạy, VLAN 99 vẫn không ra được Internet.
> Thứ hai, vEdge1 Site 300 mất fabric từ 08/10. Cấu hình không sai — **card mạng ảo bị treo chiều nhận**. Tắt bật lại cổng là mọi thứ lên lại.

---

## Slide 12 — Site 900 ra Internet có kiểm soát (≈ 1 phút)

**Nói:**
> Tuần trước Site 900 bị chặn Internet hoàn toàn. Nhưng trong doanh nghiệp, controller cần DNS, NTP, HTTPS. Nên nhóm đổi sang **có kiểm soát**: ACL trên Switch32 chỉ cho DNS, NTP, HTTPS và ping ra ngoài, mọi thứ khác bị chặn và ghi log. Nhóm áp ACL **trước** rồi mới mở NAT, để không có thời điểm nào mở toàn bộ.
> Kiểm chứng từ vManage: DNS, HTTPS, ping đều qua; HTTP và SSH bị chặn; fabric SD-WAN không bị ảnh hưởng.

---

## Slide 13 — Cảnh báo sự cố qua email (≈ 2 phút)

**Nói:**
> vManage được cấu hình tự gửi thư qua Gmail khi có alarm Critical hoặc Major. Phía mạng chỉ cần mở **đúng một luồng** SMTP 587 cho riêng vManage và khai DNS cho vManage.
> Demo: tắt cổng Internet của vEdge2 Site 200 — khoảng 20 giây sau có thư BFD down, 35 giây có thư mất kết nối điều khiển, 70 giây có thư OMP down; bật lại cổng có thư Interface State Change.
> Lần đầu thư không gửi được, Gmail báo sai tài khoản. Nhóm kiểm tra bộ đếm ACL thấy vManage vẫn kết nối được 587, rồi thử đăng nhập Gmail riêng thấy mật khẩu ứng dụng vẫn đúng — vậy lỗi là do nhập trên giao diện. Nhập lại thì gửi được.

**Nếu thầy hỏi vManage chết thì sao:** đúng là khi đó không có thư; tuần tới nhóm làm phương án B — Console đọc alarm qua API của vManage.

---

## Slide 14 — Tài liệu & báo cáo (≈ 1 phút)

**Nói:**
> Nhóm đối chiếu toàn bộ tệp cấu hình với cấu hình đang chạy và phát hiện hai chỗ lệch: System-IP thật của vManage, vBond là 10.9.3.x, và tường lửa Standby đang lưu bản cũ.
> Báo cáo LaTeX được cập nhật: Chương 3–4 viết lại phần SDN theo controller v2, thêm DIA, Site 900, cảnh báo email. Bảng tổng hợp nay có **29 kịch bản: 25 đạt, 2 đạt một phần, 1 chưa đạt, 1 chưa nghiệm thu**. Nhóm cũng bỏ 17 ảnh không liên quan hoặc lỗi thời.

---

## Slide 15 — Vấn đề còn tồn tại (≈ 1 phút)

**Nói:**
> Còn tồn tại: Site 500 chưa cấu hình phía vEdge và LAN; ba phép thử chưa làm — PC Site 100 ra Internet, cắt Internet ở S300/S400 và Mail từ VLAN 40; tường lửa Standby cần ghép HA để đồng bộ; cảnh báo phụ thuộc vManage và chưa có thư phục hồi; controller SDN vẫn là điểm lỗi đơn; controller SD-WAN chưa có NTP.

---

## Slide 16 — Nhiệm vụ tuần tới 12/10 – 18/10 (≈ 1 phút 30 giây)

**Nói:**
> Ưu tiên số một là **Site 500**: cấu hình vEdge, chứng thư, whitelist, switch và DHCP, rồi kiểm BFD, OMP, ping liên site và ra Internet. Sau đó bật đủ Site 100 để ghép HA tường lửa và làm các phép thử còn thiếu, hoàn tất ma trận DIA ở S300/S400, bật thư phục hồi và làm phương án B cho cảnh báo.
> Về báo cáo: chụp ảnh minh chứng mới cho Console, thư cảnh báo, Alarms trên vManage; hoàn thiện và chạy thử kịch bản demo có bấm giờ; rà soát báo cáo bản cuối.

---

## Slide 17 — Khó khăn gặp phải trong tuần (≈ 1 phút 30 giây)

**Nói:**
> Khó khăn lớn nhất tuần này là các lỗi **chập chờn, không để lại dấu vết rõ**: controller khựng vài phút một lần, card mạng ảo treo không có log trên thiết bị, STP Dispute chỉ xuất hiện trong vài giây lúc khôi phục. Cách nhóm xử lý là **đo liên tục** — CPU từng tiến trình, trạng thái STP mỗi 2,5 giây, bộ đếm giao diện — thay vì đoán.
> Ngoài ra là tài nguyên máy chủ: khi không thử Site 100 nhóm phải tắt để đủ RAM cho cụm SD-WAN.

---

## Slide 18 — Kết thúc (≈ 15 giây)

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
| `fail_mode=secure` | Switch mất controller vẫn giữ flow cũ, không tự học MAC. |
| Probe | Gói thăm dò controller tự gửi trên từng liên kết để biết link còn sống. |
| RSTP Dispute | Cổng nhận BPDU mâu thuẫn với vai trò của mình nên tạm chặn, chờ hết thời gian forward-delay. |
| SD-WAN | WAN định nghĩa bằng phần mềm: overlay trên nhiều đường truyền, chọn đường theo chính sách/SLA. |
| vManage / vSmart / vBond | Quản trị + alarm / control plane (OMP) / điều phối & xác thực. |
| BFD | Kiểm tra sống và đo chất lượng từng tunnel. |
| DIA | Direct Internet Access — site ra Internet ngay tại chỗ, không vòng qua campus chính. |
| `management-only` | Cổng quản trị của ASA chỉ phục vụ quản trị, không chuyển tiếp dữ liệu (quản trị ngoài băng). |
| SMTP 587 / mật khẩu ứng dụng | Cổng gửi thư có xác thực + STARTTLS / mật khẩu riêng Gmail cấp cho ứng dụng. |

## Phụ lục B — Lưu ý trước khi báo cáo

- Slide tuần này không có ảnh chụp mới của Console/vManage (Site 100 đang tắt để tiết kiệm RAM); số liệu lấy từ kết quả đo và nhật ký ngày 09–11/10. Nếu thầy muốn xem trực tiếp, cần bật Site 100 theo thứ tự: SDN controller → Dist-SW1/2 → Access → máy trạm.
- Thư cảnh báo nằm trong hộp thư nhận của nhóm — nên mở sẵn để cho thầy xem khi nói slide 13.
- Không đọc thông tin tài khoản Gmail/mật khẩu ứng dụng khi trình bày.
