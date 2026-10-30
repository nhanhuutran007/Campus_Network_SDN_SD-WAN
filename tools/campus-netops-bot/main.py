"""LangGraph agent cho lab Campus (giai đoạn 1: chỉ đọc).

Chạy terminal: `python main.py`. Telegram bot import `agent` từ đây.
"""
import logging
import os

from dotenv import load_dotenv
from langchain.tools import tool
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from campus import service

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

SYSTEM_PROMPT = """Bạn là kỹ sư vận hành mạng của đồ án "Campus Network SDN + SD-WAN" (EVE-NG).
Trả lời bằng tiếng Việt, giữ thuật ngữ kỹ thuật tiếng Anh, có cấu trúc rõ ràng.

Mạng gồm: Site 100 Campus chính (FW-ASAv HA, Core-SW1/2 IOL, 6 OVS do Ryu điều khiển, 2 vEdge),
chi nhánh 200 Cần Thơ / 300 Đà Nẵng / 400 Nha Trang (Brand-FW làm gateway + DHCP, SwitchBrand,
2 vEdge), Site 500 (vEdge-S500, SW-S500), Site 900 controller (vManage, vSmart, vBond, Switch32),
nhà cung cấp Internet (AS 64511) và MPLS (AS 64512). Underlay BGP; site 100–500 = AS 65000/65010/65020/65030/65040.
IP: octet 2 = site; VLAN /24, gateway .1, DHCP pool .100–.199; System-IP 10.200.<site>.x (300→30, 400→40, 500→50).

Công cụ:
1. list_devices(site) — xem tên thiết bị đúng trước khi gọi tool khác.
2. show_command(device, command) — chỉ lệnh show (có thể lọc `| include`).
3. ping_command(device, target, vpn) — vpn là VPN Viptela (0 transport, 1 LAN) hoặc VRF IOS.
4. diagnose(target) — chẩn đoán theo lớp có sẵn: tên vEdge (vd 'vEdge1-S300', đọc qua vManage API), 'fw'
   (FW-ASAv HA: failover, interface, OSPF, asp drop), 'sdn', 'dhcp 100', hoặc 'site 200'/'site 300'/'site 400'
   (sức khoẻ cả chi nhánh qua SD-WAN: 2 vEdge → track WAN Brand-FW → gateway → trunk switch → DHCP).
Thiết bị chi nhánh (Brand-FW, SwitchBrand, SW-S200-1…) quản trị in-band qua overlay SD-WAN: show_command dùng được.
   ƯU TIÊN dùng tool này trước khi tự gõ nhiều lệnh show; nó dừng ở lớp lỗi đầu tiên và kèm bằng chứng.
5. vmanage_devices() / vmanage_alarms(hours) — trạng thái fabric SD-WAN và alarm (đã lọc cpu/memory).
6. sdn_health() / sdn_flows(switch) — Ryu controller và flow của OVS (Dist-SW1/2, Access-SW1–4).

7. propose_change(device, commands, reason) — CHỈ ĐỀ XUẤT thay đổi; người vận hành bấm Duyệt mới áp.
8. compliance_check(target) / config_drift(device) — kiểm tuân thủ thiết kế, so lệch với configs/.
9. dhcp_status(scope) — scope/lease thật trên DHCP-Server (scope rỗng = thống kê mọi scope; vd '10.1.10.0').
FW-ASAv chỉ đọc: show_command được, kể cả `packet-tracer input inside tcp <src> 1234 <dst> 443` để mô phỏng luồng.

Quy tắc:
- Bạn KHÔNG tự thay đổi được cấu hình. Khi cần sửa, chẩn đoán trước, rồi gọi propose_change với số dòng tối thiểu
  và lý do rõ ràng; nói với người dùng rằng thay đổi chờ họ duyệt. ASA chưa hỗ trợ: đưa lệnh để làm tay.
- Chẩn đoán theo lớp: link → L2 (VLAN/trunk) → L3 (route/BGP) → dịch vụ (DHCP/control connection) → ứng dụng;
  dừng ở lớp đầu tiên sai và dẫn output làm bằng chứng.
- Tool trả về chuỗi bắt đầu bằng "LỖI:" thì KHÔNG gọi lại cùng lệnh; báo nguyên văn lỗi cho người dùng.
"""


@tool
def list_devices(site: str = "") -> str:
    """Liệt kê thiết bị của lab. site: '100', '200', '300', '400', '500', '900', 'SP' hoặc rỗng = tất cả."""
    return str(service.list_devices(site or None))


@tool
def show_command(device: str, command: str) -> str:
    """Chạy một lệnh show trên thiết bị (tên như 'Core-SW1', 'vEdge1-S200' hoặc node-id).
    Ví dụ: show_command('vEdge1-S300', 'show bfd sessions')."""
    return str(service.run_command(device, command))


@tool
def ping_command(device: str, target: str, vpn: str = "") -> str:
    """Ping từ thiết bị tới IP đích. vpn: VPN Viptela ('0', '1') hoặc VRF IOS; để rỗng nếu không cần."""
    return str(service.ping(device, target, vpn or None))


@tool
def diagnose(target: str) -> str:
    """Chẩn đoán theo lớp. target: tên vEdge ('vEdge2-S200'), 'fw', 'sdn', 'dhcp <site>' (100/200/300/400),
    hoặc 'site <200|300|400>' = sức khoẻ cả chi nhánh qua SD-WAN."""
    return str(service.diagnose(target))


@tool
def vmanage_devices() -> str:
    """Danh sách thiết bị SD-WAN theo vManage: reachability, số phiên BFD."""
    return str(service.vmanage_devices())


@tool
def vmanage_alarms(hours: int = 1) -> str:
    """Alarm vManage trong `hours` giờ gần nhất (đã lọc cpu/memory-usage)."""
    return str(service.vmanage_alarms(hours))


@tool
def sdn_health() -> str:
    """Sức khoẻ SDN Site 100 từ Ryu: OVS kết nối, link, dự phòng VLAN 99, controller khựng."""
    return str(service.sdn_health())


@tool
def sdn_flows(switch: str) -> str:
    """Tóm tắt flow OpenFlow của một OVS (theo bảng/cookie)."""
    return str(service.sdn_flows(switch))


@tool
def propose_change(device: str, commands: list[str], reason: str) -> str:
    """ĐỀ XUẤT thay đổi cấu hình (không tự áp). commands = các dòng config-mode, không gồm 'configure terminal'/
    'end'/'commit'/'write'. Bot hiện thẻ cho người vận hành bấm Duyệt; khi duyệt bot tự tạo điểm khôi phục, áp,
    kiểm sức khoẻ và rollback nếu xấu đi. Chỉ IOS/IOL, vIOS, Viptela."""
    return str(service.propose_change(device, commands, reason, "ai-agent"))


@tool
def compliance_check(target: str = "all") -> str:
    """Kiểm tuân thủ thiết kế (relay DHCP, VRRP, pool .100–.199, system-ip, màu TLOC, lọc default ISP).
    target: 'all', site '200', hoặc tên thiết bị."""
    return str(service.compliance_check(target))


@tool
def config_drift(device: str) -> str:
    """So running-config của thiết bị với file trong configs/ của repo (đã che bí mật)."""
    return str(service.drift_detail(device))


@tool
def dhcp_status(scope: str = "") -> str:
    """Scope/lease trên DHCP-Server 10.1.90.10. scope rỗng = thống kê; '10.1.10.0' = danh sách lease của scope."""
    return str(service.dhcp_status(scope or None))


TOOLS = [dhcp_status, list_devices, show_command, ping_command, diagnose, vmanage_devices, vmanage_alarms, sdn_health, sdn_flows,
         propose_change, compliance_check, config_drift]
def build_model() -> ChatOpenAI:
    """LLM qua API chuẩn OpenAI — đổi nhà cung cấp chỉ bằng .env:
    OpenRouter  LLM_BASE_URL=https://openrouter.ai/api/v1                              LLM_MODEL=nvidia/...:free
    AI Studio   LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/  LLM_MODEL=gemini-2.5-flash
    Thư viện openai tự thử lại khi gặp 429/5xx (max_retries, backoff tăng dần)."""
    base_url = os.getenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    extra = {}
    fallback = [m.strip() for m in os.getenv("LLM_FALLBACK_MODELS", "").split(",") if m.strip()]
    if fallback and "openrouter.ai" in base_url:
        # OpenRouter tự chuyển sang model sau khi model chính lỗi/quá tải
        extra["models"] = fallback
    return ChatOpenAI(
        base_url=base_url, api_key=os.getenv("API_KEY") or "missing",
        model=os.getenv("LLM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"),
        temperature=0, max_retries=4, timeout=120, extra_body=extra or None,
        # gói free OpenRouter ~20 yêu cầu/phút; AI Studio free ~10/phút → đặt LLM_RPS=0.15
        rate_limiter=InMemoryRateLimiter(requests_per_second=float(os.getenv("LLM_RPS", "0.3")),
                                         check_every_n_seconds=0.1))


model = build_model()
agent = create_react_agent(model=model, tools=TOOLS, prompt=SYSTEM_PROMPT)


if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Campus NetOps Agent (chỉ đọc) — gõ 'quit' để thoát")
    print("=" * 50)
    while True:
        try:
            user_input = input("\nCâu hỏi: ")
            if user_input.lower() in ("quit", "exit", "q"):
                break
            for s in agent.stream({"messages": [("user", user_input)]}, stream_mode="values"):
                s["messages"][-1].pretty_print()
        except KeyboardInterrupt:
            print("\nThoát...")
            break
        except Exception as e:
            logger.error(f"Error: {e}")
