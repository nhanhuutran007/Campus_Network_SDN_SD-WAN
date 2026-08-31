# NOC Monitoring – Campus SDN (Ryu)

Module giám sát mạng campus theo chuẩn NOC, chạy trực tiếp trên **SDN_CONTROLLER (10.1.99.10)** như một Ryu app. Lấy dữ liệu trực tiếp qua **OpenFlow PortStats/PortDescStats** — không cần cài agent trên switch, không dùng SNMP.

## File

- `campus_noc_monitor.py` — app Ryu: thu thập PortStats định kỳ, tính bandwidth, phát hiện tắc nghẽn, xuất REST JSON + serve Web Dashboard.
- `SDN_CONTROLLER-autostart.sh` / `SDN_CONTROLLER.sh` — đã bổ sung nạp app này cùng `campus_switch_13.py` khi khởi động Ryu.

## Các app Ryu chạy cùng controller

```
ryu-manager --ofp-tcp-listen-port 6653 \
    campus_switch_13.py \
    campus_noc_monitor.py \
    ryu.app.ofctl_rest
```

Tất cả chung WSGI của Ryu → **REST & Dashboard nằm trên port 8080** (cùng với `ofctl_rest`).

## Truy cập Dashboard NOC (từ PC-Management / PC quản lý)

Mở trình duyệt tại PC trong VLAN 99 management:

```
http://10.1.99.10:8080/
```

Dashboard hiển thị (tự refresh mỗi 3 giây):
- **KPI**: tổng Rx/Tx (Mbps), số switch online, số cảnh báo.
- **Biểu đồ bandwidth tổng** (Rx/Tx) theo thời gian (Chart.js, lịch sử ~60s).
- **Bảng chi tiết từng port**: Rx/Tx, % utilization (thanh màu), trạng thái OK/WARN/HIGH.
- **Danh sách switch** (vai trò, trạng thái kết nối).
- **Cảnh báo tắc nghẽn** (congestion) — sắp theo mức độ.

## REST API NOC (JSON, northbound)

| Endpoint | Ý nghĩa |
|---|---|
| `GET /noc/switches` | Danh sách switch + trạng thái kết nối + uptime |
| `GET /noc/ports` (`?dpid=`) | Chi tiết port: rate Rx/Tx, pps, lỗi, drop, %util |
| `GET /noc/congestion` | Danh sách cảnh báo tắc nghẽn (WARN/HIGH) |
| `GET /noc/topology` | Topo switch cho mục đích vẽ sơ đồ |
| `GET /noc/summary` | Tổng hợp (switch up, tổng BW, số cảnh báo) |
| `GET /noc/history` | Lịch sử sample (cho biểu đồ) |

Ví dụ:
```bash
curl http://10.1.99.10:8080/noc/summary
curl http://10.1.99.10:8080/noc/congestion
curl http://10.1.99.10:8080/noc/ports
```

## Cách tính bandwidth & phát hiện tắc nghẽn

- **Bandwidth**: lấy hiệu `rx_bytes` / `tx_bytes` giữa 2 lần poll chia cho khoảng thời gian (interval 5s). Kết quả = bytes/s → hiển thị Mbps/Gbps.
- **Utilization (%)**: `(rx+tx) / cur_speed × 100` (tốc độ port lấy từ PortDesc `cur_speed`).
- **Ngưỡng cảnh báo** (trong `CONGEST_LOW` / `CONGEST_HIGH`):
  - `>= 70%` → **WARN**
  - `>= 90%` → **HIGH**

## Kiểm tra nhanh

```bash
# Trên EVE host, sau khi có route tới 10.1.99.10 (xem md "truy cập controller"):
curl -s http://10.1.99.10:8080/noc/summary | python -m json.tool

# Các switch phải hiện đủ 6 (5, 8, 68, 66, 70, 69) trong /noc/switches
curl -s http://10.1.99.10:8080/noc/switches
```

## Lưu ý

- Dashboard dùng **Chart.js từ CDN** → PC truy cập cần có Internet, hoặc tải chart.umd.min.js local về và chỉnh `<script src>`.
- Port OpenFlow 6653: OpenFlow control. Port 8080: REST + Dashboard.
- Nếu muốn tăng độ mượt/độ phân giải, giảm `POLL_INTERVAL` (mặc định 5s) trong `campus_noc_monitor.py`.
