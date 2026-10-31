# Kịch bản thuyết trình — Báo cáo tiến độ tuần 26/10 – 01/11/2026

**Đề tài:** Xây dựng mạng Campus Network sử dụng SDN và SD-WAN
**Nhóm:** Trần Hữu Nhân (52300235) — Nguyễn Nhật Hào (52300198)
**Slide:** `report.pdf` (19 slide) · **Thời lượng dự kiến:** 13–15 phút + hỏi đáp

> Cách dùng: phần **Nói** là lời thoại gợi ý, đọc tự nhiên, không cần thuộc từng chữ.
> Phần **Nhấn mạnh** là ý phải nói được dù quên lời. Phần **Nếu thầy hỏi** chuẩn bị sẵn câu trả lời ngắn.
> Gợi ý chia người: một bạn nói slide 1–12 (mục tiêu, SD-WAN, kiểm thử tích hợp, lỗi định tuyến), bạn còn lại nói slide 13–19 (NetOps Bot, việc còn lại, kế hoạch, khó khăn). Có thể đổi theo phần mỗi bạn trực tiếp làm.

---

## Slide 1 — Trang bìa (≈ 30 giây)

**Nói:**
> Em chào thầy. Nhóm em gồm hai thành viên là Trần Hữu Nhân và Nguyễn Nhật Hào. Hôm nay nhóm em xin báo cáo tiến độ tuần từ 26/10 đến 01/11/2026 của đề tài **"Xây dựng mạng Campus Network sử dụng SDN và SD-WAN"**.

---

## Slide 2 — Nội dung báo cáo (≈ 20 giây)

**Nói:**
> Bài báo cáo gồm năm phần: **mục tiêu**, **kết quả thực hiện trong tuần**, **công việc chưa hoàn thành**, **kế hoạch tuần tới** và **khó khăn** nhóm gặp phải.

---

## Slide 3 — Mục tiêu đề tài (≈ 45 giây)

**Nói:**
> Nhắc lại mục tiêu tổng quát: nhóm em xây dựng mạng campus nhiều cơ sở trên EVE-NG. Campus chính dùng **SDN** — controller Ryu điều khiển sáu switch Open vSwitch; các cơ sở nối với nhau bằng **SD-WAN** Cisco Viptela qua hai đường Internet và MPLS. Kèm theo là firewall ASAv chạy HA, DMZ, Server Farm và các dịch vụ DNS, DHCP, Web, Mail.
>
> So với các tuần trước, nhóm em bổ sung thêm một mục tiêu mới là **vận hành tự động**: một bot quản trị mạng qua Telegram, em sẽ trình bày ở phần sau.

**Nhấn mạnh:** mục tiêu mới "NetOps Bot" là phần mở rộng, không thay thế các mục tiêu cũ.

---

## Slide 4 — Topology tổng thể (≈ 30 giây)

**Nói:**
> Đây là topology hiện tại trên EVE-NG, gồm 70 node: Campus chính Site 100, ba chi nhánh Cần Thơ, Đà Nẵng, Nha Trang, Site 500 mở rộng và Site 900 chứa ba controller SD-WAN. Hai nhà cung cấp Internet và MPLS chạy BGP.

---

## Slide 5 — Mục tiêu của tuần và mức độ hoàn thành (≈ 1 phút)

**Nói:**
> Tuần trước nhóm em đặt ra sáu việc. Kết quả là: **theo dõi vEdge** đã hoàn thành; **Site 500** đã hoàn thành: hai vEdge lên fabric, Brand-FW-S500 làm firewall-as-core, switch SW-S500 và máy trạm nhận IP qua DHCP. **Đo lặp SD-WAN** mới làm được một phần — đã có số liệu failover đầu tiên. Còn **failover firewall**, **fast-failover cho Distribution** và **bản nháp báo cáo cuối kỳ** thì chưa làm.
>
> Lý do là trong tuần nhóm em phát sinh thêm ba việc: kiểm thử tích hợp bật toàn bộ 70 node, sửa hai lỗi làm mất Internet phát hiện trong lúc kiểm thử, và xây dựng NetOps Bot. Các việc chưa làm em đã đưa lên đầu kế hoạch tuần tới.

**Nhấn mạnh:** nói thẳng phần chưa làm và lý do, trước khi thầy hỏi.

**Nếu thầy hỏi "sao không làm failover firewall như kế hoạch?":**
> Dạ, khi bật toàn hệ thống để kiểm thử thì phát hiện mất Internet ở nhiều site, nhóm em ưu tiên sửa lỗi đó trước vì nếu không thì các phép đo sau đều sai. Failover firewall là việc số 1 của tuần tới.

---

## Slide 6 — Tổng quan tiến độ theo hạng mục (≈ 40 giây)

**Nói:**
> Nhìn tổng thể: phần thiết kế, hạ tầng campus, chi nhánh, SD-WAN và SDN đã hoàn thành. Site 500 nay cũng đã xong: hai vEdge, Brand-FW-S500, switch và máy trạm nhận DHCP. Đang làm có ba hạng mục: **kiểm thử tích hợp** — phần chức năng đạt, còn kịch bản sự cố; **NetOps Bot** là hạng mục mới; và **báo cáo, demo**.

---

## Slide 7 — SD-WAN: trạng thái fabric trên vManage (≈ 45 giây)

**Nói:**
> Đây là ảnh chụp giao diện vManage ngày 31/10. Cả **10 vEdge**, trong đó có **hai vEdge của Site 500**, và ba controller đều ở trạng thái reachable, health xanh. Cột BFD cho thấy các phiên BFD đều lên đủ: Site 100 là 16 trên 16, mỗi vEdge chi nhánh 10 trên 10.

**Nếu thầy hỏi "vManage báo 14 thiết bị, sao chỉ thấy 13 dòng?":**
> Dạ, có một dòng là vEdge đã khai trong danh sách nhưng chưa đăng ký nên không có tên, nhóm em lọc theo "vEdge" để ảnh gọn. 13 thiết bị đang dùng thì đều reachable.

**Nếu thầy hỏi "icon cảnh báo màu cam ở vManage là gì?":**
> Dạ, đó là cảnh báo về sức khỏe của chính máy vManage; vManage vẫn reachable và giữ kết nối với controller nên không ảnh hưởng tới fabric. Giao diện cũng đang nhắc tài khoản cơ sở dữ liệu cấu hình còn để mặc định, nhóm em sẽ đổi.

---

## Slide 8 — SD-WAN: các tunnel IPsec (≈ 30 giây)

**Nói:**
> Trang Tunnels cho thấy **124 tunnel IPsec** giữa các vEdge qua hai màu biz-internet và MPLS, kể cả các tunnel tới Site 500. Mất gói trung bình gần như bằng 0.

**Nếu thầy hỏi "sao latency trên vManage ~40 ms mà đo được 4–12 ms?":**
> Dạ, số trên vManage là latency của gói BFD đo bên trong vEdge, có cả thời gian xử lý của máy ảo. Số 4–12 ms ở slide sau là ping thật qua overlay. Nhóm em dùng số ping để so sánh giữa các site.

---

## Slide 9 — Đo failover link WAN tại Site 200 (≈ 1 phút)

**Nói:**
> Đây là kết quả đo độ tin cậy đầu tiên. Công cụ web ở Site 900 ping liên tục qua overlay, rồi nhóm em cắt uplink của vEdge 1 Site 200. Sau hai lần đo, thời gian khôi phục RTO từ **7,68 đến 8,25 giây**, trung bình **7,96 giây**; tỉ lệ khôi phục gói khoảng **77%**.
>
> Con số khoảng 8 giây khớp với BFD mặc định của Viptela: gửi hello mỗi 1 giây, mất 7 lần liên tiếp mới kết luận tunnel chết. So với SDN ở campus chính có fast-failover dưới 0,3 giây thì SD-WAN đang chậm hơn nhiều.
>
> Hai lần đo là chưa đủ, tuần tới nhóm em đo 3–5 lần mỗi site và thử giảm chu kỳ BFD để so sánh.

**Nhấn mạnh:** 8 s = BFD 1 s × 7; mới 2 lần nên chưa kết luận.

**Nếu thầy hỏi "PRR là gì?":**
> Dạ, PRR là tỉ lệ gói ping trả lời được trong suốt cửa sổ đo, kể cả lúc đang chuyển đường. 77% nghĩa là khoảng 23% gói bị mất trong thời gian chuyển đường.

**Nếu thầy hỏi "giảm BFD có hại gì không?":**
> Dạ, chu kỳ ngắn thì phát hiện nhanh hơn nhưng dễ báo nhầm khi máy ảo bị khựng, nên nhóm em sẽ đo cả số lần báo nhầm để chọn mức cân bằng.

---

## Slide 10 — So sánh hiệu năng Campus chính và chi nhánh (≈ 1 phút)

**Nói:**
> Nhóm em đo delay, jitter, mất gói theo hai loại đường: LAN trong từng site, và WAN qua SD-WAN. Kết quả: đường WAN **không mất gói ở cả bốn site**, delay từ 3,8 đến 12 ms. Site 400 Nha Trang có delay và jitter cao nhất vì có vài mẫu ping vọt lên 25–50 ms, cần đo lặp để xem do tải máy ảo hay do đường đi.
>
> Riêng Site 100 chỉ đo được 3 trên 5 tuyến LAN: hai tuyến tới Web Server và DHCP-Server mất hết gói. Nguyên nhân là firewall Site 100 chặn ICMP từ vùng SD-WAN vào Server Farm và DMZ — đúng chính sách bảo mật. Nhóm em sẽ đổi cách đo chứ không mở firewall chỉ để đo.

**Nhấn mạnh:** mất gói ở 2 tuyến LAN Site 100 là do chính sách, không phải lỗi mạng.

---

## Slide 11 — Kiểm thử tích hợp toàn hệ thống (≈ 1 phút)

**Nói:**
> Ngày 25/10 nhóm em bật đồng thời cả 70 node và kiểm tra từng cụm: SDN 6/6 switch, 13/13 liên kết, 7/7 máy trạm nhận DHCP; firewall HA Active và Standby Ready; SD-WAN 12/12 thiết bị, 92/92 phiên BFD; chi nhánh 9/9 VPC và 3 PC Linux nhận DHCP và truy cập được Web, Mail, DNS ở campus chính; cả bốn site ra Internet. Ngày 30/10 thêm kiểm tra quản trị in-band tới 12 thiết bị chi nhánh.
>
> Như vậy toàn bộ kiểm thử **chức năng** đã đạt; tuần tới chuyển sang kiểm thử **sự cố**.

---

## Slide 12 — Hai lỗi định tuyến làm mất Internet (≈ 1 phút 15 giây)

**Nói:**
> Trong lúc kiểm thử, nhóm em gặp hai lỗi.
>
> Lỗi thứ nhất: khi Site 500 lên fabric thì **mọi site mất Internet**. Lần theo BGP trên router Internet thì thấy router này nhận default route từ vEdge Site 500, nên đường ra Internet của các site bị kéo sai hướng. Nhóm em thêm bộ lọc BGP chặn default route đi vào từ neighbor Site 500; sau đó cả bốn site ra Internet lại, Site 500 vẫn trong fabric.
>
> Lỗi thứ hai: Site 100 mất Internet. Core-SW1 và Core-SW2 quảng bá OSPF cùng cost nên firewall có hai đường bằng nhau, nhưng ASA không chia tải qua hai interface khác nhau, nên gói chiều về đi vào sai interface bị drop. Nhóm em đặt cost 10 trên các SVI của Core-SW2 để chỉ còn một đường ưu tiên.

**Nhấn mạnh:** cả hai lỗi chỉ lộ ra khi bật **toàn bộ** hệ thống — đó là lý do cần kiểm thử tích hợp.

**Nếu thầy hỏi "vậy Core-SW2 còn dự phòng không?":**
> Dạ còn. Cost 10 chỉ làm đường qua Core-SW2 kém ưu tiên hơn; khi Core-SW1 hỏng, OSPF tự chuyển sang Core-SW2.

---

## Slide 13 — Campus NetOps Bot: kiến trúc in-band (≈ 1 phút 15 giây)

**Nói:**
> Phần mới của tuần là **Campus NetOps Bot** — trợ lý vận hành mạng qua Telegram. Quản trị viên nhắn lệnh hoặc hỏi bằng ngôn ngữ tự nhiên; bot dùng LangGraph và một mô hình ngôn ngữ lớn để chọn công cụ phù hợp: SSH tới switch và firewall, đọc REST API của vManage và Ryu, hoặc đọc DHCP.
>
> Điểm khác là bot được cài **ngay trong topology**, trên DHCP-Server của Site 100, và quản trị theo kiểu **in-band**: đi qua chính mạng dữ liệu. Như vậy bot cũng là một "người dùng" của mạng — mạng hỏng thì bot biết đầu tiên.
>
> Về an toàn: bot chỉ trả lời các chat được cho phép, mặc định chỉ chạy lệnh đọc, tự che mật khẩu trong kết quả, và dùng tài khoản `netops` riêng; mỗi thiết bị chỉ cho SSH từ hai địa chỉ quản trị.

**Nếu thầy hỏi "AI có thể tự ý đổi cấu hình không?":**
> Dạ không. AI chỉ được gọi các công cụ đọc. Mọi thay đổi phải qua lệnh `/change` và phải có người bấm duyệt trên Telegram.

**Nếu thầy hỏi "dùng LLM nào?":**
> Dạ, bot gọi LLM qua API chuẩn OpenAI nên đổi nhà cung cấp chỉ cần sửa file cấu hình; hiện nhóm em dùng một model miễn phí qua OpenRouter.

---

## Slide 14 — Ba giai đoạn đã triển khai (≈ 1 phút)

**Nói:**
> Bot được làm theo ba giai đoạn. **Giai đoạn 1** chỉ đọc: danh mục 47 thiết bị khớp topology, lệnh `/show`, `/health` và hỏi đáp tự nhiên. **Giai đoạn 2** cảnh báo và chẩn đoán: bot tự nhắn khi vEdge mất kết nối hoặc OVS rời controller; lệnh `/diag` chẩn đoán **theo lớp** và dừng ở lớp đầu tiên sai. **Giai đoạn 3** thay đổi có kiểm soát: `/change` phải được duyệt, và nếu thiết bị mất kết nối sau khi áp thì **tự rollback**; thêm kiểm tra tuân thủ, sao lưu và so sánh cấu hình.
>
> Ví dụ `/diag site 400` kiểm tra lần lượt vEdge, WAN của Brand-FW, gateway, trunk rồi DHCP. Chính lệnh này đã phát hiện một **lệch thiết kế có thật**: uplink của hai switch phòng ban Site 400 lên trunk nhờ DTP tự thỏa thuận chứ không cấu hình tường minh. Nhóm em giữ lại lỗi này để demo: bot phát hiện, sửa bằng `/change`, rồi tự rollback nếu có sự cố.

**Nhấn mạnh:** bot tìm ra lỗi thật mà nhóm chưa biết.

**Nếu thầy hỏi "rollback làm thế nào?":**
> Dạ, với switch IOS bot dùng `configure replace` về bản cấu hình đã lưu; với vEdge Viptela dùng `commit confirmed` — nếu không xác nhận trong thời gian quy định thì thiết bị tự quay về.

---

## Slide 15 — Mở rộng ra chi nhánh và kiểm thử (≈ 45 giây)

**Nói:**
> Để bot quản trị được chi nhánh qua overlay SD-WAN, nhóm em cấu hình thêm 12 thiết bị: Brand-FW, SwitchBrand và hai switch phòng ban ở mỗi site. Switch có tài khoản `netops`, SSH v2 và ACL chỉ cho hai IP quản trị; Brand-FW xác thực SSH bằng tài khoản cục bộ.
>
> Kết quả: từ Site 100 ping được 15/15 IP quản trị chi nhánh; bộ selftest chạy trên chính DHCP-Server đạt **23/23**; có 71 unit test; chẩn đoán qua vManage cho 8/8 vEdge đạt cả 6 lớp; và lệnh lẫn câu hỏi tự nhiên trên Telegram đều chạy thật.

---

## Slide 16 — Vấn đề còn tồn tại (≈ 45 giây)

**Nói:**
> Những việc còn tồn tại: chưa kiểm thử sự cố firewall HA, VRRP và cắt một màu WAN; đo lặp SD-WAN mới 2 lần ở một site; Site 500 đã xong LAN nhưng chưa kiểm thử tích hợp Web, Mail, DNS và Internet như ba chi nhánh; SDN khi mất liên kết Distribution–Core vẫn gián đoạn 2 đến 3,7 giây vì chưa có fast-failover cho tầng này; NetOps Bot chưa có rollback cho ASA; và báo cáo cuối kỳ chưa bắt đầu bản nháp.

---

## Slide 17 — Kế hoạch tuần tới 02/11 – 08/11 (≈ 1 phút)

**Nói:**
> Tuần tới nhóm em ưu tiên kiểm thử sự cố vì hạn kiểm thử tích hợp là 10/11. Cụ thể: một, failover firewall HA và VRRP; hai, cắt một màu WAN xem BFD và AAR chuyển đường, đo lặp failover 3–5 lần mỗi site, đo khôi phục khi mất vSmart; ba, kiểm thử tích hợp Site 500 và đưa vào NetOps Bot; bốn, nếu kịp thì thử fast-failover cho uplink Distribution–Core.
>
> Phần NetOps và báo cáo: thêm rollback cho ASA và hoàn thiện kịch bản demo sửa trunk Site 400; đo lại tuyến LAN Site 100 theo cách mới; và bắt đầu viết chương kết quả và chương NetOps Bot của báo cáo cuối kỳ.

---

## Slide 18 — Khó khăn (≈ 1 phút)

**Nói:**
> Khó khăn chính trong tuần:
> - Có những lỗi **chỉ lộ ra khi bật toàn hệ thống**, như việc Site 500 làm mất Internet mọi site.
> - **Hành vi riêng của ASA**: không chia tải qua hai interface khác nhau; tài khoản mới bị bắt đổi mật khẩu ở lần SSH đầu và đăng nhập console không xóa được yêu cầu này; ASA còn cấm mật khẩu có chuỗi ký tự liên tiếp.
> - SSH client trên switch IOL đời cũ chỉ hỗ trợ SHA-1, phải tạm nới thuật toán trên ASA rồi trả lại.
> - LLM miễn phí bị giới hạn tần suất, nhóm em chuyển sang API chuẩn OpenAI, thêm cơ chế thử lại và model dự phòng.
> - Triển khai trên Windows Server 2012 R2 là hệ điều hành cũ nên phải đóng gói bộ cài offline; có lần một lỗi cú pháp khi chép mã làm bot khởi động lại liên tục, nên nhóm em thêm test kiểm cú pháp trước khi triển khai.
> - Cuối cùng, chính sách firewall chặn ICMP làm sai số đo tuyến LAN Site 100.

---

## Slide 19 — Cảm ơn (≈ 10 giây)

**Nói:**
> Phần báo cáo của nhóm em đến đây là hết. Em cảm ơn thầy đã lắng nghe, nhóm em xin nhận câu hỏi và góp ý của thầy.

---

## Chuẩn bị thêm trước buổi báo cáo

- Mở sẵn `report.pdf` và `../baocao-tuan/main.pdf` (báo cáo tuần bản chữ) phòng khi thầy hỏi chi tiết.
- Nếu lab còn bật: mở sẵn Telegram, sẵn sàng gõ `/diag site 400` để demo bot phát hiện lỗi trunk Site 400 (khoảng 30 giây).
- Số liệu cần nhớ: RTO **7,96 s** (7,68–8,25 s), PRR **76,75%**; delay WAN **3,8–12 ms**, mất gói WAN **0%**; selftest **23/23**; **10/10 vEdge**, **124 tunnel**.
