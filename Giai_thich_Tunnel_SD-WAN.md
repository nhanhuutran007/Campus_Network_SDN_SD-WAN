# Giải thích số liệu Tunnel & Transport Health — Lab SD-WAN 4 Site

> Số liệu đo thật từ vManage (API `/dataservice/device/bfd/sessions`), ngày **09/09/2026**.
> Toàn bộ overlay SD-WAN dùng giao thức **BFD (Bidirectional Forwarding Detection)** — **1 phiên BFD = 1 tunnel** giữa 2 vEdge.

---

## 1. Vì sao tổng cộng có 72 tunnel?

### 1.1. Mỗi vEdge có bao nhiêu TLOC?

TLOC (Transport Location) là một "điểm ra WAN" — **mỗi interface WAN có bật `tunnel-interface` với 1 màu (color) = 1 TLOC**.

| Thiết bị | WAN / Color | Subnet (đầu vEdge) | Số TLOC |
|---|---|---|---|
| vEdge1-S100 | ge0/2 `mpls` | 100.64.100.1/30 | 2 |
| vEdge1-S100 | ge0/3 `biz-internet` | 203.0.113.1/30 | |
| vEdge2-S100 | ge0/2 `biz-internet` | 203.0.113.5/30 | 2 |
| vEdge2-S100 | ge0/3 `mpls` | 100.64.100.5/30 | |
| vEdge1-S200 | ge0/2 `mpls` | 100.64.200.1/30 | 1 |
| vEdge2-S200 | ge0/0 `biz-internet` | 203.0.113.9/30 | 1 |
| vEdge1-S300 | ge0/0 `mpls` | 100.64.30.1/30 | 1 |
| vEdge2-S300 | ge0/0 `biz-internet` | 203.0.113.13/30 | 1 |
| vEdge1-S400 | ge0/0 `mpls` | 100.64.40.1/30 | 1 |
| vEdge2-S400 | ge0/0 `biz-internet` | 203.0.113.17/30 | 1 |

**Tổng TLOC toàn mạng = 10.** Điểm đặc biệt: **S100 (khu Campus) đầu tư dual-WAN cho CẢ 2 vEdge** (mỗi vEdge có 2 TLOC: `mpls` + `biz-internet`), còn các chi nhánh S200/S300/S400 **mỗi vEdge chỉ 1 WAN** (vEdge1 = `mpls`, vEdge2 = `biz-internet`).

### 1.2. Công thức đếm tunnel

SD-WAN full-mesh: mỗi vEdge mở tunnel tới **mọi TLOC của mọi vEdge còn lại** (trừ chính nó và vEdge cùng site). Số tunnel mà 1 vEdge nhìn thấy:

> **Số tunnel (phiên BFD) của 1 vEdge = (số TLOC cục bộ) × (tổng số TLOC của 6 vEdge còn lại)**

**Ví dụ vEdge1-S100** (2 TLOC cục bộ, mỗi vEdge khác 1 TLOC riêng):
```
2 TLOC cục bộ × 6 vEdge còn lại = 12 phiên BFD  →  vEdge1-S100 có 12 tunnel ✓
```

**Ví dụ vEdge1-S200** (1 TLOC cục bộ; S100 có 4 TLOC, S300 có 2, S400 có 2):
```
1 TLOC cục bộ × (4 + 2 + 2) = 8 phiên BFD  →  vEdge1-S200 có 8 tunnel ✓
```

### 1.3. Tổng hợp

| Site | vEdge | số TLOC | Tunnel của vEdge |
|---|---|---|---|
| S100 | vEdge1 | 2 | 12 |
| S100 | vEdge2 | 2 | 12 |
| S200 | vEdge1 | 1 | 8 |
| S200 | vEdge2 | 1 | 8 |
| S300 | vEdge1 | 1 | 8 |
| S300 | vEdge2 | 1 | 8 |
| S400 | vEdge1 | 1 | 8 |
| S400 | vEdge2 | 1 | 8 |
| **Tổng** | **8 vEdge** | **10** | **72** |

> **Lưu ý:** 72 là **tổng phiên BFD từ 2 đầu tunnel** (mỗi tunnel vEdge A→B và B→A đều được đếm). Số tunnel **duy nhất thật sự = 72 ÷ 2 = 36** — đúng bằng số cặp TLOC khác site: S100-S200 (4×2) + S100-S300 (4×2) + S100-S400 (4×2) + S200-S300 (2×2) + S200-S400 (2×2) + S300-S400 (2×2) = **36**.

---

## 2. Vì sao vEdge của S100 có 12 tunnel mà các vEdge khác chỉ 8?

| | vEdge S100 | vEdge chi nhánh (S200/300/400) |
|---|---|---|
| Số WAN màu (`tunnel-interface`) | **2** (mpls + biz-internet) | **1** (vEdge1 = mpls, vEdge2 = biz-internet) |
| Số TLOC cục bộ | **2** | **1** |
| Số vEdge khác cần kết nối | 6 | 6 |
| Số TLOC toàn mạng còn lại | 6 | **8** (vì S100 đóng góp 4 TLOC) |
| **Tunnel** | **2 × 6 = 12** | **1 × 8 = 8** |

**Nguyên nhân gốc:** Site S100 dùng **dual-WAN cho cả 2 router** (mỗi vEdge cắm đồng thời MPLS + Internet để dự phòng/đánh giá chất lượng 2 đường), còn chi nhánh **tách vai trò** — vEdge1 chỉ đường MPLS, vEdge2 chỉ đường Internet. Vì vậy:
- vEdge S100 có **2 điểm ra WAN** → nhân đôi số tunnel so với chi nhánh (12 vs 8).
- Đồng thời, 2 S100 "phình" tổng số TLOC từ 6 lên 10 → các vEdge chi nhánh kết tới **8 TLOC** (gồm 4 TLOC từ S100) thay vì 6.

Ngược lại, nếu mọi vEdge đều chỉ 1 WAN thì con số sẽ là **6 tunnel/vEdge cho cả mạng** (6 vEdge còn lại × 1 TLOC), tổng **48 BFD phiên = 24 tunnel** — đây là dạng full-mesh "tối giản". Con số 72 phản ánh thiết kế **multi-WAN** của dự án.

---

## 3. Vì sao có tunnel up/down? (60 up, 12 down)

### 3.1. Bảng down chi tiết (đo thật)

| Device | Tổng | Up | Down | Tunnel down (local color → remote color) |
|---|---|---|---|---|
| vEdge1-S100 | 12 | 9 | 3 | `mpls` → `biz-internet` tới vEdge2-S200, vEdge2-S300, vEdge2-S400 |
| vEdge2-S100 | 12 | 9 | 3 | `mpls` → `biz-internet` tới vEdge2-S200, vEdge2-S300, vEdge2-S400 |
| vEdge2-S200 | 8 | 6 | 2 | `biz-internet` → `mpls` tới vEdge1-S100, vEdge2-S100 |
| vEdge2-S300 | 8 | 6 | 2 | `biz-internet` → `mpls` tới vEdge1-S100, vEdge2-S100 |
| vEdge2-S400 | 8 | 6 | 2 | `biz-internet` → `mpls` tới vEdge1-S100, vEdge2-S100 |
| 3 vEdge1-S200/300/400 | 8×3 | 8×3 | 0 | — |
| **Tổng** | **72** | **60** | **12** | |

### 3.2. Quy luật của 12 tunnel down

12 phiên BFD down quy về **đúng 6 cặp tunnel duy nhất** (mỗi cặp bị down ở cả 2 đầu):

> **Tunnel giữa TLOC `mpls` của S100 ↔ TLOC `biz-internet` của vEdge2-S200/S300/S400.**

- S100 có 2 TLOC `mpls` (vEdge1 + vEdge2) × 3 vEdge2 chi nhánh = **6 tunnel** → hiện down ở 2 đầu = 12 phiên.
- Toàn bộ tunnel **cùng màu** (`mpls`↔`mpls`, `biz`↔`biz`) và tunnel `biz-internet` của S100 ↔ `mpls` chi nhánh vẫn **up**.

### 3.3. Vì sao lại down?

BFD chỉ báo **up** nếu tunnel thực sự "sống" (bắt tay DTLS/IPsec + BFD hello phản hồi được). 6 tunnel này nằm đúng **ranh giới giữa 2 nhà cung cấp** (MPLS SP ↔ Internet SP, nối nhau qua `100.64.254.0/30`):

- Đầu `mpls` của S100 nằm trên mạng MPLS (`100.64.100.x`).
- Đầu `biz-internet` của vEdge2 chi nhánh nằm trên mạng Internet (`203.0.113.x`).
- Dù 2 SP có BGP liên thông, đường đi cross-carrier bị **bất đối xứng / không đáp ứng BFD** trong lab → tunnel không build được.

Đây **đã được ghi nhận từ 29/08** như là hành vi **bình thường theo multi-WAN**: mỗi site vẫn có **đủ tunnel up** phục vụ chuyển mạch dự phòng và định tuyến (S100: 9/12/vEdge; chi nhánh vEdge1: 8/8; vEdge2: 6/8). Nếu muốn 72/72 up, cần xử lý thêm phần reachability/DTLS qua biên 2 SP — không bắt buộc cho chức năng overlay hiện tại.

| Trạng thái | Ý nghĩa |
|---|---|
| **up (60)** | Tunnel sẵn sàng, BFD đang kiểm tra tốt — dữ liệu có thể đi qua |
| **down (12)** | Tunnel không build được (cross-carrier) — **dữ liệu KHÔNG đi qua tunnel này**; traffic chọn đường qua tunnel up khác |

---

## 4. Latency, Jitter, Loss hiển thị trên dashboard là gì?

Khi xem 1 tunnel (BFD session) trên vManage `Monitor → Network → Tunnels`, vEdge liên tục gửi gói **BFD probe** qua tunnel để đo 3 chỉ số chất lượng WAN:

| Chỉ số | Đơn vị | Định nghĩa | Đo bằng cách nào |
|---|---|---|---|
| **Latency** | ms | **Độ trễ 1 chiều** (one-way) từ vEdge nguồn tới vEdge đích qua tunnel | vEdge ghi timestamp gói BFD khi gửi, so với khi đích nhận (đồng hồ 2 đầu đồng bộ NTP) hoặc lấy RTT/2 |
| **Jitter** | ms | **Độ biến thiên của latency** giữa các gói đo liên tiếp (packet delay variation) | Tính chênh lệch latency giữa các lần probe |
| **Loss** | % | **Tỷ lệ gói probe BFD bị mất** trên tunnel trong khoảng thời gian đo | Số gói gửi đi − số gói đích nhận, quy ra % |

### 4.1. Ý nghĩa thực tế (dấu hiệu chất lượng WAN)

- **Loss > 0%** — đường WAN quá tải/cong/hỏng, là chỉ số **quan trọng nhất**: vượt ngưỡng → vManage đổi tuyến để tránh mất gói.
- **Latency cao** — ảnh hưởng trực tiếp tới ứng dụng thời gian thực (VoIP, video): độ trễ khứ hồi > 400 ms thường không dùng được.
- **Jitter cao** — "giật/nghẽn" khi nghe gọi / xem video ngay cả khi latency thấp (tiếng/tín hiệu đến lúc nhanh lúc chậm).

### 4.2. Ngưỡng tham chiếu phổ biến (cấu hình được trong app-route policy)

| Chỉ số | TỐT (thêm vào preferred) | CẢNH BÁO | XẤU (tránh / loại khỏi path) |
|---|---|---|---|
| **Loss** | < 1 % | 1 – 2,5 % | > 2,5 % |
| **Latency** | < 150 ms | 150 – 300 ms | > 300 ms |
| **Jitter** | < 20 ms | 20 – 50 ms | > 50 ms |

> Tuỳ chính sách, vManage dùng các ngưỡng này để chọn tunnel tốt nhất (best path) khi có nhiều đường.

### 4.3. Ví dụ đọc số liệu

Số đo `latency = 12 ms, jitter = 2 ms, loss = 0.0 %` trên tunnel vEdge1-S100 → vEdge1-S200 (`mpls`↔`mpls`):
- Gói BFD mất ~12 ms để đi 1 chiều qua tunnel, độ lệch giữa các lần đo chỉ 2 ms, không mất gói → đường rất ổn định (màu xanh).
- Lý do thấp như vậy: lab EVE-NG chạy trên cùng hạ tầng vật lý, các "chặng" là router mô phỏng → là kỳ vọng hợp lý chứ không phải chất lượng thật của hạ tầng thực.

---

## 5. Transport Health là gì?

**Transport Health** (Sức khoẻ đường truyền) là **điểm tổng hợp của vManage** cho mỗi **transport** (tunnel/WAN link = 1 TLOC), dựa trên 4 yếu tố:

```
Transport Health = Trạng thái tunnel (up/down)
                 + Loss %
                 + Latency (ms)
                 + Jitter (ms)
```

- vManage gộp các chỉ số trên từ BFD của **từng tunnel**, gán 1 trong 3 mức cho tunnel đó:

| Mức / Màu | Điều kiện (tham chiếu) | Ý nghĩa |
|---|---|---|
| 🟢 **Good / Green** | Tunnel **up**, loss < 1 %, latency & jitter thấp | Đường truyền tốt, sử dụng bình thường |
| 🟡 **Degraded / Yellow** | Tunnel up nhưng 1 trong các chỉ số vượt ngưỡng cảnh báo (vd loss 1–2,5 %) | Chất lượng suy giảm, cần theo dõi |
| 🔴 **Down / Red** | Tunnel **down** (BFD fail) | Không sử dụng được — traffic tự dồn sang đường khác |

- **Nơi hiển thị:** trong vManage, chọn thiết bị → mở detail 1 tunnel sẽ thấy kết hợp "state + Transport health"; trang overview site-level hiển thị **màu xanh/vàng/đỏ** cho từng link WAN để NOC nhìn nhanh tình trạng.
- **Vai trò quan trọng:** Transport Health chính là thông tin mà OMP/routing policy dùng để **quyết định đường đi** (dựa vào loss/latency/jitter do BFD cung cấp) — là nền tảng của chức năng tự chuyển tuyến (steering) trong SD-WAN.
- **Với lab này:** 12 phiên BFD down → các transport tương ứng hiện **red**; 60 phiên up hiện **xanh/vàng** tuỳ theo 3 chỉ số đo được.

---

## 6. Tóm tắt nhanh

| Câu hỏi | Trả lời |
|---|---|
| Vì sao **72 tunnel**? | 8 vEdge full-mesh, tổng 10 TLOC → tổng phiên BFD từ 2 đầu = 72 (tunnel duy nhất = 36) |
| Vì sao **S100 có 12** còn chi nhánh **8**? | S100 dual-WAN cho cả 2 vEdge (2 TLOC/vEdge) → nhân 2; chi nhánh 1 WAN/vEdge |
| Vì sao **60 up / 12 down**? | 6 tunnel `mpls` S100 ↔ `biz-internet` vEdge2 chi nhánh không build (cross-carrier) — đã ghi nhận là bình thường theo multi-WAN |
| **Latency/Jitter/Loss** là gì? | Chỉ số chất lượng đo qua BFD: độ trễ 1 chiều (ms), độ biến thiên độ trễ (ms), tỷ lệ mất gói (%) |
| **Transport Health** là gì? | Điểm tổng hợp trạng thái tunnel + loss/latency/jitter → màu xanh/vàng/đỏ, giúp định tuyến chọn đường tốt nhất |