<div align="center">

# Xây dựng mạng Campus Network sử dụng SDN và SD-WAN

**Mô phỏng hạ tầng mạng đại học đa cơ sở trên EVE-NG — Campus LAN do SDN điều khiển, kết nối liên chi nhánh bằng SD-WAN overlay**

![Platform](https://img.shields.io/badge/Platform-EVE--NG-blue)
![SDN](https://img.shields.io/badge/SDN-Ryu%20%7C%20OpenFlow%201.3-green)
![SD-WAN](https://img.shields.io/badge/SD--WAN-Cisco%20Viptela%2020.10-orange)
![Security](https://img.shields.io/badge/Security-Cisco%20ASAv%20HA-red)
![NetOps](https://img.shields.io/badge/NetOps-Telegram%20ChatOps%20%2B%20AI-blueviolet)
![Status](https://img.shields.io/badge/Status-%C4%90ang%20ho%C3%A0n%20thi%E1%BB%87n-yellow)

</div>

---

## Mục lục

- [Giới thiệu](#giới-thiệu)
- [Tính năng chính](#tính-năng-chính)
- [Kiến trúc hệ thống](#kiến-trúc-hệ-thống)
- [Quy hoạch địa chỉ](#quy-hoạch-địa-chỉ)
- [Công nghệ sử dụng](#công-nghệ-sử-dụng)
- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [Yêu cầu môi trường](#yêu-cầu-môi-trường)
- [Triển khai lab](#triển-khai-lab)
- [Kiểm thử và xác minh](#kiểm-thử-và-xác-minh)
- [Tiến độ dự án](#tiến-độ-dự-án)
- [Tài liệu liên quan](#tài-liệu-liên-quan)
- [Nhóm thực hiện](#nhóm-thực-hiện)

---

## Giới thiệu

Hạ tầng mạng của trường đại học phải phục vụ đồng thời nhiều khoa, phòng máy, khu hành chính, dịch vụ dùng chung và các cơ sở ở xa. Mạng truyền thống cấu hình thủ công trên từng thiết bị nên khó mở rộng, khó đồng bộ chính sách và xử lý sự cố chậm.

Đề tài xây dựng một mô hình **Campus Network kết hợp SDN và SD-WAN**, mô phỏng đầy đủ trên **EVE-NG** (70 node):

- **Campus chính (Site 100)** theo mô hình 3 lớp Core – Distribution – Access; lớp Distribution/Access là **Open vSwitch do SDN Controller điều khiển** qua OpenFlow 1.3.
- **3 chi nhánh** (Cần Thơ, Đà Nẵng, Nha Trang) theo mô hình *Firewall-as-Core* gọn nhẹ.
- **SD-WAN Cisco Viptela** kết nối các cơ sở qua 2 đường truyền **Internet** và **MPLS**, có SLA, định tuyến theo ứng dụng (AAR) và chính sách dữ liệu tập trung.
- **Campus NetOps Bot**: vận hành mạng qua Telegram (ChatOps) với AI agent, quản trị in-band thiết bị Site 100 và chi nhánh qua overlay SD-WAN.

### Mục tiêu

1. Thiết kế kiến trúc Campus phân cấp, có dự phòng ở các lớp Core, Firewall và WAN.
2. Quy hoạch VLAN và địa chỉ IP thống nhất cho tất cả các site.
3. Quản lý tập trung lớp chuyển mạch Campus bằng SDN Controller.
4. Kết nối đa cơ sở bằng SD-WAN overlay mã hoá IPsec, chọn đường theo SLA.
5. Kiểm thử chức năng: DHCP, định tuyến liên VLAN và liên site, failover, dịch vụ nội bộ.
6. Tự động hoá vận hành: chẩn đoán theo lớp, cảnh báo chủ động, thay đổi cấu hình có duyệt và tự rollback.

### Phạm vi

Đề tài dừng ở mức thiết kế logic và mô phỏng trên EVE-NG, chưa triển khai trên hạ tầng vật lý. Toàn bộ cấu hình thiết bị, script và tài liệu vận hành đều nằm trong repository này.

---

## Tính năng chính

| Nhóm | Tính năng |
|---|---|
| **SDN Campus** | Ryu (OpenFlow 1.3) điều khiển 6 OVS: học MAC theo VLAN, chống vòng L2 bằng cây chuyển tiếp do controller tính (OVS không chạy STP), tự chuyển sang đường dự phòng khi một Distribution switch hỏng; **fast-failover trên data plane** (BFD + OpenFlow group FAST_FAILOVER) cho uplink Access, mất 1 uplink chỉ mất 1–2 gói |
| **Giám sát SDN** | Campus SDN Console trên Ryu: topology, đo tải (PortStats/TableStats, CPU Core qua SNMP), tab Sức khoẻ và Kịch bản kiểm thử S1–S6 tự chạy |
| **SD-WAN** | vManage / vSmart / vBond, 9 vEdge, 2 màu TLOC (`biz-internet`, `mpls`), BFD full-mesh, service VPN 1, SLA class + AAR + data policy |
| **Underlay WAN** | eBGP giữa vEdge và nhà cung cấp (Internet AS 64511, MPLS AS 64512) |
| **Dự phòng** | VRRP trên Core-SW1/2, ASAv Active/Standby failover, 2 vEdge và 2 transport mỗi site, Access dual-home lên 2 Distribution |
| **Bảo mật** | ASAv phân vùng inside/DMZ/Server Farm, OSPF Area 0 giữa FW và Core, VLAN quản trị 99 tách biệt, ASDM |
| **Dịch vụ** | DHCP (Windows Server 2012 R2 + relay), DNS `campus.internal`, Web HTTPS (Nginx), Mail (hMailServer), Syslog (Kiwi) |
| **Công cụ đo** | `scripts/campus_ping_tool.py`, `campus_web.py`, `sdwan_reliability.py`: đo latency/loss/jitter/throughput, so sánh Campus chính với chi nhánh, RTO/PRR khi failover, availability |
| **NetOps / ChatOps** | Bot Telegram chạy trong topo (DHCP-Server Site 100): `/diag` chẩn đoán theo lớp (vEdge qua vManage API, FW HA, SDN, DHCP, cả chi nhánh), cảnh báo vManage/Ryu, `/change` có duyệt + tự rollback, `/compliance`, `/backup`, `/drift`; hỏi đáp tự nhiên qua LLM (LangGraph) — chi tiết [`tools/campus-netops-bot/`](tools/campus-netops-bot/README.md) |

---

## Kiến trúc hệ thống

![Topology tổng thể](docs/hinh/topo_tongthe.jpg)

```mermaid
flowchart TB
    subgraph SP["Nhà cung cấp dịch vụ"]
        INET["Internet<br/>AS 64511"]
        MPLS["MPLS<br/>AS 64512"]
    end

    subgraph S900["Site 900 — SD-WAN Controllers"]
        VM["vManage"]
        VS["vSmart"]
        VB["vBond"]
    end

    subgraph S100["Site 100 — Campus chính"]
        VE100["vEdge1/2-S100"]
        FW["FW-ASAv<br/>Active / Standby"]
        CORE["Core-SW1 / Core-SW2<br/>VRRP · OSPF"]
        DIST["Dist-SW1 / Dist-SW2<br/>OVS"]
        ACC["Access-SW1..4<br/>OVS"]
        CTRL["SDN Controller<br/>Ryu"]
        SRV["Server Farm / DMZ<br/>NetOps Bot"]
        VE100 --- FW --- CORE --- DIST --- ACC
        CORE --- SRV
        CTRL -. OpenFlow .- DIST
        CTRL -. OpenFlow .- ACC
    end

    subgraph BR["Site 200 / 300 / 400 — Chi nhánh"]
        VEB["vEdge1/2"]
        BFW["Brand-FW<br/>Gateway + DHCP"]
        BSW["SwitchBrand + SW phòng ban"]
        VEB --- BFW --- BSW
    end

    VE100 === INET & MPLS
    VEB === INET & MPLS
    S900 --- INET & MPLS
    SRV -. SSH in-band qua overlay .- BFW
```

### Các site

| Site | Vai trò | Thành phần chính |
|---|---|---|
| **100** | Campus chính | FW-ASAv HA, Core-SW1/2 (IOL), Dist-SW1/2 + Access-SW1–4 (OVS), SDN Controller, Server Farm, DMZ, 2 vEdge |
| **200** | Chi nhánh Cần Thơ | Brand-FW (ASAv), SwitchBrand, SW55/56, 2 vEdge |
| **300** | Chi nhánh Đà Nẵng | Brand-FW (ASAv), SwitchBrand, SW58/59, 2 vEdge |
| **400** | Chi nhánh Nha Trang | Brand-FW (ASAv), SwitchBrand, SW57/60, 2 vEdge |
| **500** | Chi nhánh mới | vEdge Site 500 (đã lên fabric), SW-S500, VPC11/12 — WAN Internet + MPLS, AS 65040; LAN đang triển khai |
| **900** | SD-WAN Controllers | vManage, vSmart, vBond, Switch32 (LAN controller) |
| **SP** | Nhà cung cấp | Router Internet, router MPLS |

Campus chính và chi nhánh cố ý dùng hai kiến trúc khác nhau. Campus chính cần phân lớp và dự phòng đầy đủ; chi nhánh nhỏ dùng firewall làm gateway và DHCP để giảm số thiết bị và điểm lỗi.

---

## Quy hoạch địa chỉ

**Quy ước:** `10.<site>.<vlan>.0/24`, trong đó octet thứ hai là site (1 = Campus chính, 2 = Cần Thơ, 3 = Đà Nẵng, 4 = Nha Trang, 5 = Site 500, 9 = Controller). Gateway luôn là `.1`, máy chủ dùng `.10`/`.11`, DHCP cấp dải `.100–.199`.

### Campus chính (Site 100)

| VLAN | Tên | Subnet |
|---:|---|---|
| 10 | Khoa CNTT | `10.1.10.0/24` |
| 20 | Khoa Toán – Thống kê | `10.1.20.0/24` |
| 30 | Khoa Luật | `10.1.30.0/24` |
| 40 | Hành chính | `10.1.40.0/24` |
| 90 | Server Farm | `10.1.90.0/24` |
| 99 | Management (SDN control plane, ASDM) | `10.1.99.0/24` |
| — | DMZ | `10.1.1.0/28` |

### Chi nhánh

| Site | VLAN phòng ban | Subnet |
|---|---|---|
| 200 Cần Thơ | 60 Nông nghiệp, 70 Y tế | `10.2.60.0/24`, `10.2.70.0/24` |
| 300 Đà Nẵng | 80 Du lịch, 90 Tài chính | `10.3.80.0/24`, `10.3.90.0/24` |
| 400 Nha Trang | 50 Thủy sản, 60 Lữ hành | `10.4.50.0/24`, `10.4.60.0/24` |

Mỗi chi nhánh có thêm VLAN 99 để quản trị (`10.<site>.99.0/24`: Brand-FW `.1`, SwitchBrand `.2`, switch phòng ban `.11`/`.12`), quản trị in-band từ Site 100 qua overlay SD-WAN.

### WAN và SD-WAN

| Hạng mục | Giá trị |
|---|---|
| Transport Internet | `203.0.113.0/24` (màu `biz-internet`) |
| Transport MPLS | `100.64.x.x/30` (màu `mpls`) |
| System-IP vEdge | `10.200.<site>.x` (site 300/400/500/900 dùng octet `30`/`40`/`50`/`90`) |
| Controller LAN | `10.9.0.0/24`: vManage `.10`, vSmart `.11`, vBond `.12` |
| BGP ASN | Internet 64511, MPLS 64512; Site 100/200/300/400/500 = 65000/65010/65020/65030/65040 |

Bảng đầy đủ nằm trong [`campus_network_sdn_sdwan.md`](campus_network_sdn_sdwan.md) và [`configs/README.md`](configs/README.md).

---

## Công nghệ sử dụng

| Thành phần | Công nghệ / phiên bản |
|---|---|
| Nền tảng mô phỏng | EVE-NG |
| SDN Controller | Ryu (OpenFlow 1.3); ONOS 2.7.0 đã thử chạy song song rồi dừng (làm controller khựng) |
| Switch SDN | Open vSwitch trên Ubuntu |
| SD-WAN | Cisco Viptela 20.10.1 (vManage, vSmart, vBond, vEdge) |
| Firewall | Cisco ASAv (failover Active/Standby, ASDM 7.20) |
| Core / chi nhánh L2 | Cisco IOL |
| Giao thức | OSPF Area 0, eBGP, VRRP, 802.1Q, OMP, BFD, IPsec, DTLS |
| Dịch vụ | Windows Server 2012 R2 (DHCP, DNS), Nginx, hMailServer, Kiwi Syslog |
| Công cụ & tài liệu | Python 3 (Tkinter, matplotlib, paramiko), Bash, systemd, LaTeX |
| NetOps Bot | Python 3.11, python-telegram-bot, LangGraph + LangChain, Paramiko (SSH in-band), REST vManage/Ryu, LLM qua API chuẩn OpenAI (OpenRouter; đổi được sang Google AI Studio) |

---

## Cấu trúc thư mục

```text
.
├── Campus Network SDN SD-WAN.unl     # File lab EVE-NG (70 node, config nhúng)
├── campus_network_sdn_sdwan.md       # Tài liệu thiết kế: topology, bảng IP/VLAN/link
├── configs/                          # Cấu hình từng thiết bị theo site
│   ├── 01-Site100-Campus/            # Core, FW, OVS scripts, app Ryu, systemd, dịch vụ
│   ├── 02-Site200-CanTho/
│   ├── 03-Site300-DaNang/
│   ├── 04-Site400-NhaTrang/
│   ├── 05-Site900-Controller/        # vManager-33, vSmart-34, vBond-35 (running-config đầy đủ), Switch32/61, vEdge-Spare
│   ├── 06-ServiceProvider/           # Router Internet và MPLS (BGP)
│   ├── 07-Site500/                   # vEdge65 (chi nhánh Site 500)
│   └── README.md                     # Ánh xạ node-id, cách nạp config, thứ tự khởi động
├── scripts/                          # Công cụ chạy trên laptop (chạy từ gốc repo: python scripts/<tên>.py)
│   ├── campus_ping_tool.py           #   đo latency/loss/jitter, failover SD-WAN, VLAN (GUI)
│   ├── campus_web.py                 #   giao diện web giám sát (dùng web/index.html)
│   ├── campus_throughput.py          #   đo throughput
│   ├── sdwan_monitor.py              #   đọc API vManage
│   ├── sdwan_reliability.py          #   độ tin cậy SD-WAN: RTO/PRR failover, availability
│   ├── sdwan_onboard.py, sdwan_certsign.py, sdwan_autosign_check.py  # onboard/ký cert vEdge
│   └── sdn_controller_startup.sh     #   script khởi động SDN Controller
├── tools/
│   └── campus-netops-bot/            # NetOps Bot: Telegram ChatOps + AI agent, chẩn đoán, thay đổi có duyệt,
│                                     #   bộ cài offline cho Windows Server (chạy trên DHCP-Server Site 100)
├── web/                              # Giao diện của campus_web.py
├── log/                              # Kết quả đo (CSV/PNG/JSON), log/sdn-eval: số liệu đánh giá SDN
├── docs/
│   ├── de-tai/                       # Đề bài, mô tả đề tài
│   ├── huong-dan/                    # Hướng dẫn vận hành: ký cert/CSR vEdge, cài OVS, GUI,
│   │                                 #   tunnel SD-WAN, kết nối EVE-NG
│   ├── ket-qua/                      # Tài liệu kết quả: SD-WAN failover, chính sách tập trung
│   ├── tien-do/                      # Bảng theo dõi tiến độ (md + xlsx)
│   └── hinh/                         # topo_tongthe.jpg (dùng chung README + slide)
└── baocao/
    ├── cuoi-ky/                      # Báo cáo đồ án cuối kỳ (LaTeX)
    ├── giua-ky/                      # Báo cáo giữa kỳ (LaTeX)
    ├── baocao-tuan/                  # Báo cáo tiến độ tuần (LaTeX + PDF)
    └── slide-tuan/                   # Slide báo cáo tiến độ hằng tuần
```

---

## Yêu cầu môi trường

- **EVE-NG** (Community hoặc Pro), khuyến nghị tối thiểu 16 vCPU và 64 GB RAM để chạy toàn bộ lab. Có thể bật từng site nếu tài nguyên hạn chế.
- **Image** (tự chuẩn bị, không đi kèm repo vì lý do bản quyền):
  - Cisco IOL (L2/L3), Cisco ASAv
  - Cisco Viptela 20.10.1: `vtmgmt`, `vtsmart`, `vtbond`, `vtedge`
  - Ubuntu có Open vSwitch và Ryu (template `linux-ubuntu-ovs-16p`)
  - Windows Server 2012 R2, Windows 7, Ubuntu 18.04 Desktop, VPCS
- **Máy trạm:** Python 3.8+ nếu dùng công cụ kiểm thử:

```bash
pip install matplotlib paramiko numpy
```

---

## Triển khai lab

1. **Nhập lab:** copy `Campus Network SDN SD-WAN.unl` vào `/opt/unetlab/labs/` trên EVE-NG và sửa quyền:
   ```bash
   /opt/unetlab/wrappers/unl_wrapper -a fixpermissions
   ```
2. **Nạp cấu hình:** 47 node đã có config nhúng trong `.unl`. Các node còn lại (Viptela controller, Windows, Linux/OVS) cấu hình theo file trong `configs/`. Chi tiết xem [`configs/README.md`](configs/README.md).
3. **Khởi động theo thứ tự:**
   1. Service Provider (Internet, MPLS) → Switch32/Switch61 → vManage, vSmart, vBond → các vEdge.
   2. Site 100: Core-SW1/2 → FW-ASAv → Server Farm/DMZ → SDN Controller → Dist/Access → PC.
   3. Chi nhánh: Brand-FW → SwitchBrand/SW → PC.
4. **SDN:** controller chạy `campus-ryu.service` (OpenFlow `6653`, REST + Campus SDN Console `8080`). OVS tự khôi phục cấu hình qua `campus-ovs-restore.service`.
5. **SD-WAN:** onboard vEdge (CSR → ký cert → whitelist trên cả 3 controller) theo [`docs/huong-dan/cách ký và add vedge.md`](docs/huong-dan/cách%20ký%20và%20add%20vedge.md).
6. **NetOps Bot (tuỳ chọn):** đóng gói bằng `tools/campus-netops-bot/scripts/build_windows_bundle.py`, chép vào `C:\netops` trên DHCP-Server, điền `.env` (token Telegram, API key LLM), chạy `install.ps1`, kiểm bằng `scripts/selftest.py`. Thiết bị cần user `netops` + SSH in-band (đã có trong `configs/`). Chi tiết [`tools/campus-netops-bot/README.md`](tools/campus-netops-bot/README.md).

---

## Kiểm thử và xác minh

| Hạng mục | Lệnh / cách kiểm tra | Kết quả mong đợi |
|---|---|---|
| SDN kết nối | `curl http://10.1.99.10:8080/stats/switches` | Đủ 6 DPID `{5, 8, 66, 68, 69, 70}` |
| DHCP Campus | `ip dhcp` trên VPC VLAN 10–40 | Nhận `10.1.<vlan>.1xx`, ping được gateway và liên VLAN |
| DHCP chi nhánh | `show dhcpd state` trên Brand-FW, `ip dhcp` trên VPC | Nhận `10.<site>.<vlan>.1xx` |
| Control plane SD-WAN | `show control connections` trên vEdge | vBond, vManage, vSmart đều Up |
| Data plane SD-WAN | `show bfd sessions`, `show omp routes` | BFD Up, có route service VPN 1 |
| Liên site | Ping VPC giữa Site 200/300/400 | Thông qua overlay |
| Failover WAN | `scripts/campus_ping_tool.py` → SD-WAN Failover Test | Đo RTO khi tắt một màu WAN |
| Dịch vụ | `https://www.campus.internal`, gửi/nhận mail | Truy cập được từ PC các site |
| Độ tin cậy SD-WAN | `scripts/sdwan_reliability.py` | RTO/PRR khi cắt vEdge (24/10: RTO trung bình 7,96 s), availability từng site |
| NetOps Bot | `scripts\selftest.py` trên DHCP-Server; `/diag site 300` trên Telegram | Selftest đạt hết (30/10: 23/23); chẩn đoán dừng ở lớp lỗi đầu tiên kèm bằng chứng |

---

## Tiến độ dự án

- [x] Thiết kế topology, quy hoạch IP/VLAN/ASN
- [x] Core IOL, FW-ASAv HA + ASDM, OSPF FW ↔ Core, DMZ, Server Farm
- [x] SDN Campus: Ryu điều khiển 6 OVS, chống vòng L2, failover, tự khôi phục sau reboot, fast-failover data plane, Campus SDN Console
- [x] DHCP Campus end-to-end qua relay
- [x] SD-WAN: 3 controller, PKI, vEdge onboard, BGP underlay, BFD full-mesh
- [x] Service VPN 1, SLA/AAR/data policy, liên thông chi nhánh
- [x] Dịch vụ Web / Mail / DNS / Syslog; Internet có kiểm soát cho 4 site
- [x] Đo hiệu năng và độ tin cậy: so sánh Campus chính ↔ chi nhánh, RTO/PRR failover SD-WAN, 5 mục tiêu SDN
- [x] Campus NetOps Bot: ChatOps Telegram + AI agent, chẩn đoán theo lớp, thay đổi có duyệt + rollback, quản trị in-band Site 100 và chi nhánh
- [ ] Site 500: LAN (switch + PC)
- [ ] Ma trận kiểm thử tích hợp đầy đủ (FW failover, cắt 1 màu WAN xem AAR, mất controller, cold-start toàn lab)
- [ ] Hoàn thiện báo cáo cuối kỳ, slide và video demo (đã có báo cáo giữa kỳ + báo cáo tuần)

Chi tiết xem [`docs/tien-do/BangTheoDoiTienDo.md`](docs/tien-do/BangTheoDoiTienDo.md).

---

## Tài liệu liên quan

| Tài liệu | Nội dung |
|---|---|
| [`campus_network_sdn_sdwan.md`](campus_network_sdn_sdwan.md) | Thiết kế chi tiết, bảng IP/VLAN/link |
| [`configs/README.md`](configs/README.md) | Ánh xạ node-id, cách nạp config, thứ tự khởi động |
| [`configs/01-Site100-Campus/README_NOC.md`](configs/01-Site100-Campus/README_NOC.md) | App giám sát NOC trên Ryu |
| [`tools/campus-netops-bot/README.md`](tools/campus-netops-bot/README.md) | NetOps Bot: kiến trúc, lệnh Telegram, triển khai trên DHCP-Server, quản trị chi nhánh qua SD-WAN |
| [`docs/tien-do/BangTheoDoiTienDo.md`](docs/tien-do/BangTheoDoiTienDo.md) | Bảng theo dõi tiến độ (cập nhật 30/10/2026) |
| [`docs/huong-dan/Giai_thich_Tunnel_SD-WAN.md`](docs/huong-dan/Giai_thich_Tunnel_SD-WAN.md) | Cơ chế tunnel, TLOC, BFD trong SD-WAN |
| [`docs/huong-dan/`](docs/huong-dan/) | Hướng dẫn cài OVS, ký cert vEdge, xem GUI vManage |
| [`baocao/cuoi-ky/main.pdf`](baocao/cuoi-ky/main.pdf) | Báo cáo đồ án |

---

## Nhóm thực hiện

| Họ tên | MSSV |
|---|---|
| **Trần Hữu Nhân** | `52300235` |
| **Nguyễn Nhật Hào** | `52300198` |

Đồ án thực hiện cho mục đích học tập và nghiên cứu. Các image Cisco và phần mềm thương mại không được phân phối kèm repository này.
