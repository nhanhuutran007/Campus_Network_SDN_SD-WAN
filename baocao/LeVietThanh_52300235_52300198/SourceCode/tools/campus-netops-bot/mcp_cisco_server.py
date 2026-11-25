"""MCP server cho lab Campus (giai đoạn 1: chỉ đọc).

Tool nhận TÊN thiết bị, không nhận mật khẩu: credentials đọc từ file cục bộ lúc chạy.
Thử: `npx @modelcontextprotocol/inspector python mcp_cisco_server.py`
"""
import asyncio

from mcp.server.fastmcp import FastMCP

from campus import service

mcp = FastMCP(name="campus-netops", instructions="""
    Bạn vận hành lab Campus Network SDN + SD-WAN. Gọi list_devices trước để lấy tên thiết bị đúng.
    Đọc bằng show/ping/traceroute; thay đổi cấu hình chỉ qua suggest_change → người duyệt trên Telegram. Ưu tiên tool diagnose khi tìm nguyên nhân sự cố. Chẩn đoán theo lớp, dẫn output làm bằng chứng.
    """)


async def _call(fn, *args, timeout=150.0) -> str:
    try:
        return str(await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=timeout))
    except asyncio.TimeoutError:
        return "LỖI: Quá thời gian chờ thiết bị."


@mcp.tool()
async def list_devices(site: str = "") -> str:
    """Liệt kê thiết bị. site: 100/200/300/400/500/900/SP, rỗng = tất cả."""
    return str(service.list_devices(site or None))


@mcp.tool()
async def show_command(device: str, command: str) -> str:
    """Chạy một lệnh show trên thiết bị (tên hoặc node-id), vd ('Core-SW1', 'show vrrp brief')."""
    return await _call(service.run_command, device, command)


@mcp.tool()
async def ping_command(device: str, target: str, vpn: str = "") -> str:
    """Ping từ thiết bị tới đích; vpn = VPN Viptela hoặc VRF IOS (tuỳ chọn)."""
    return await _call(service.ping, device, target, vpn or None)


@mcp.tool()
async def diagnose(target: str) -> str:
    """Chẩn đoán theo lớp: tên vEdge, 'sdn', hoặc 'dhcp <site>'. Dừng ở lớp lỗi đầu tiên, kèm bằng chứng."""
    return await _call(service.diagnose, target, timeout=300.0)


@mcp.tool()
async def vmanage_devices() -> str:
    """Thiết bị SD-WAN theo vManage (reachability, BFD)."""
    return await _call(service.vmanage_devices)


@mcp.tool()
async def vmanage_alarms(hours: int = 1) -> str:
    """Alarm vManage trong N giờ (đã lọc cpu/memory-usage)."""
    return await _call(service.vmanage_alarms, hours)


@mcp.tool()
async def sdn_health() -> str:
    """Sức khoẻ SDN Site 100 từ Ryu controller."""
    return await _call(service.sdn_health)


@mcp.tool()
async def sdn_flows(switch: str) -> str:
    """Tóm tắt flow OpenFlow của một OVS."""
    return await _call(service.sdn_flows, switch)


@mcp.tool()
async def compliance_check(target: str = "all") -> str:
    """Kiểm tuân thủ thiết kế đồ án: 'all', site '200', hoặc tên thiết bị."""
    return await _call(service.compliance_check, target, timeout=600.0)


@mcp.tool()
async def config_drift(device: str) -> str:
    """So running-config với configs/ trong repo."""
    return await _call(service.drift_detail, device)


@mcp.tool()
async def suggest_change(device: str, commands: list[str], reason: str) -> str:
    """Soạn đề xuất thay đổi cấu hình. MCP không áp cấu hình: trả về khối /change để người vận hành
    dán vào Telegram (nơi có nút Duyệt, kiểm sau thay đổi và rollback)."""
    from campus import change, inventory
    dev = inventory.resolve(device)
    if dev is None:
        return f"LỖI: không có thiết bị '{device}'."
    errs = change.validate(dev.platform, commands)
    if errs:
        return "LỖI: đề xuất bị chặn:\n- " + "\n- ".join(errs)
    return "Dán vào Telegram để tạo yêu cầu chờ duyệt:\n\n" + "\n".join([f"/change {dev.name}", f"# {reason}"] + commands)


if __name__ == "__main__":
    mcp.run(transport="stdio")
