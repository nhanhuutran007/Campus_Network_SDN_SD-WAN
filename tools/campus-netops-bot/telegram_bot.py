"""Telegram ChatOps cho lab Campus (chỉ đọc).

Chỉ chat_id trong TELEGRAM_ALLOWED_CHAT_IDS được dùng bot.
Lệnh trực tiếp (không qua LLM):
  /devices [site]        /show <thiết bị> <lệnh show>     /ping <thiết bị> <đích> [vpn]
  /diag <vEdge|fw|sdn|dhcp 100>   /dhcp [scope]   /alarms [giờ]   /health   /sdn   /flows <OVS>
  /change <thiết bị> + các dòng lệnh   /approve /cancel /undo <id>   /changes
  /compliance [site|thiết bị]   /backup [site|thiết bị]   /drift <thiết bị>
Tin nhắn thường → LangGraph agent.
Giai đoạn 2: vòng cảnh báo đọc alarm vManage + sức khoẻ Ryu mỗi ALERT_INTERVAL giây, đẩy về
ALERT_CHAT_IDS kèm nút 🩺 Chẩn đoán / 🔕 Tắt 1 giờ.
"""
import asyncio
import html
import itertools
import logging
import os
import time

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from campus import service
from campus.alerts import AlertMonitor
from campus.change import ChangeError

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)   # httpx log cả URL có token bot
logger = logging.getLogger(__name__)

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def _ids(var: str) -> set[int]:
    return {int(x) for x in os.getenv(var, "").replace(" ", "").split(",") if x}


ALLOWED = _ids("TELEGRAM_ALLOWED_CHAT_IDS")
ALERT_CHATS = _ids("ALERT_CHAT_IDS") or ALLOWED
ALERT_ENABLED = os.getenv("ALERT_ENABLED", "1") == "1"
ALERT_INTERVAL = max(20, int(os.getenv("ALERT_INTERVAL", "60")))
APPROVERS = _ids("CHANGE_APPROVER_IDS")          # user id được duyệt; rỗng = mọi chat được phép
FOUR_EYES = os.getenv("CHANGE_FOUR_EYES", "0") == "1"
STATE_FILE = os.getenv("ALERT_STATE_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "alert_state.json"))
TG_LIMIT = 3900

# callback_data của Telegram tối đa 64 byte → lưu khoá dài trong bảng, nút chỉ mang số
_CB: dict[str, str] = {}
_cb_seq = itertools.count(1)


def _cb(value: str) -> str:
    k = str(next(_cb_seq))
    _CB[k] = value
    if len(_CB) > 2000:
        for old in list(_CB)[:500]:
            _CB.pop(old, None)
    return k


def allowed(update: Update) -> bool:
    ok = update.effective_chat and update.effective_chat.id in ALLOWED
    if not ok:
        logger.warning("Từ chối chat_id=%s", update.effective_chat.id if update.effective_chat else None)
    return bool(ok)


async def reply_long(message, text: str, pre: bool = True):
    """Telegram giới hạn 4096 ký tự/tin — chia nhỏ; output thiết bị để trong <pre>."""
    for i in range(0, max(len(text), 1), TG_LIMIT):
        part = text[i:i + TG_LIMIT]
        if pre:
            await message.reply_html(f"<pre>{html.escape(part)}</pre>")
        else:
            await message.reply_text(part)


async def _run(update: Update, waiting: str, fn, *args):
    msg = await update.message.reply_text(waiting)
    res = await asyncio.to_thread(fn, *args)
    await msg.delete()
    await reply_long(update.message, str(res))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        await update.message.reply_text(f"⛔ Chat này chưa được cấp quyền (chat_id {update.effective_chat.id}).")
        return
    await update.message.reply_html(
        "🤖 <b>Campus NetOps Bot</b> (chỉ đọc)\n\n"
        "/devices [site] — danh sách thiết bị\n"
        "/show &lt;thiết bị&gt; &lt;lệnh show&gt;\n"
        "/ping &lt;thiết bị&gt; &lt;đích&gt; [vpn]\n"
        "/diag &lt;vEdge | fw | sdn | dhcp 100&gt; — chẩn đoán theo lớp (vEdge qua vManage API)\n"
        "/dhcp [scope] — scope/lease trên DHCP-Server, vd /dhcp 10.1.10.0\n"
        "/alarms [giờ] — alarm vManage (đã lọc cpu/memory)\n"
        "/health — vManage + SDN tổng quan\n"
        "/sdn, /flows &lt;OVS&gt; — Ryu controller\n"
        "/change &lt;thiết bị&gt; + lệnh ở các dòng sau — đổi cấu hình (duyệt → áp → kiểm → tự rollback)\n"
        "/changes, /undo &lt;id&gt; — lịch sử, hoàn tác\n"
        "/compliance, /backup, /drift &lt;thiết bị&gt; — tuân thủ, sao lưu, so lệch configs/\n\n"
        f"🔔 Cảnh báo chủ động: {'BẬT' if ALERT_ENABLED else 'TẮT'} (mỗi {ALERT_INTERVAL} s)\n"
        "Hoặc hỏi tự nhiên: <i>\"Vì sao PC Site 300 không nhận IP?\"</i>")


async def devices(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if allowed(update):
        await reply_long(update.message, str(service.list_devices(context.args[0] if context.args else None)))


async def show(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Cú pháp: /show <thiết bị> <lệnh show>")
        return
    await _run(update, "⏳ Đang mở console...", service.run_command, context.args[0], " ".join(context.args[1:]))


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Cú pháp: /ping <thiết bị> <đích> [vpn]")
        return
    vpn = context.args[2] if len(context.args) > 2 else None
    await _run(update, "⏳ Đang ping...", service.ping, context.args[0], context.args[1], vpn)


async def diag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    if not context.args:
        await update.message.reply_text("Cú pháp: /diag vEdge1-S300 | /diag sdn | /diag dhcp 200")
        return
    await _run(update, "🩺 Đang chẩn đoán theo lớp...", service.diagnose, " ".join(context.args))


async def alarms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    hours = int(context.args[0]) if context.args and context.args[0].isdigit() else 1
    await _run(update, "⏳ Đang đọc alarm vManage...", service.vmanage_alarms, hours)


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    msg = await update.message.reply_text("⏳ Đang đọc vManage và Ryu...")
    vm, sdn = await asyncio.gather(asyncio.to_thread(service.vmanage_devices), asyncio.to_thread(service.sdn_health))
    await msg.delete()
    await reply_long(update.message, f"{vm}\n\n{sdn}")


async def dhcp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if allowed(update):
        await _run(update, "⏳ Đang đọc DHCP-Server...", service.dhcp_status, context.args[0] if context.args else None)


async def sdn(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if allowed(update):
        await _run(update, "⏳ Đang đọc Ryu...", service.sdn_health)


async def flows(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    if not context.args:
        await update.message.reply_text("Cú pháp: /flows Dist-SW1")
        return
    await _run(update, "⏳ Đang đọc flow...", service.sdn_flows, context.args[0])


# ------------------------------------------------------------------ Giai đoạn 3: thay đổi có duyệt
def _who(update: Update) -> str:
    u = update.effective_user
    return f"tg:{u.id} {u.full_name}" if u else "tg:?"


def can_approve(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    return uid in APPROVERS if APPROVERS else allowed(update)


def _card_markup(rid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("✅ Duyệt", callback_data=f"approve|{_cb(rid)}"),
                                  InlineKeyboardButton("❌ Huỷ", callback_data=f"cancel|{_cb(rid)}")]])


async def send_card(message, req) -> None:
    await message.reply_html(f"<pre>{html.escape(req.card())}</pre>", reply_markup=_card_markup(req.id))


async def change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/change <thiết bị> rồi các dòng lệnh ở các dòng sau; dòng bắt đầu bằng '#' là lý do."""
    if not allowed(update):
        return
    lines = update.message.text.splitlines()
    head = lines[0].split(maxsplit=1)
    if len(head) < 2 or len(lines) < 2:
        await update.message.reply_text("Cú pháp:\n/change SW-S500\n# lý do thay đổi\ninterface Loopback99\n"
                                        " description test")
        return
    reason = " ".join(l.lstrip("# ").strip() for l in lines[1:] if l.startswith("#"))
    cmds = [l for l in lines[1:] if l.strip() and not l.startswith("#")]
    msg = await update.message.reply_text("⏳ Đang kiểm lệnh và đọc running-config...")
    try:
        req = await asyncio.to_thread(service.changes().propose, head[1].strip(), cmds, reason, _who(update),
                                      update.effective_chat.id)
    except ChangeError as e:
        await msg.edit_text(f"⛔ {e}")
        return
    await msg.delete()
    await send_card(update.message, req)


async def run_change(app: Application, chat_id: int, rid: str, approver: str, undo: bool = False) -> None:
    """Chạy yêu cầu trong thread; tiến trình cập nhật trực tiếp vào một tin nhắn."""
    loop = asyncio.get_running_loop()
    status = await app.bot.send_message(chat_id, f"⏳ #{rid} {'hoàn tác' if undo else 'đang áp'}...")
    lines: list[str] = []

    def progress(m: str):
        lines.append(m)
        text = f"⏳ #{rid}\n" + "\n".join(lines)
        asyncio.run_coroutine_threadsafe(status.edit_text(text[-TG_LIMIT:]), loop)

    mgr = service.changes()
    try:
        if undo:
            req = await asyncio.to_thread(mgr.undo, rid, approver, progress)
        else:
            req = await asyncio.to_thread(mgr.approve_and_run, rid, approver, False, progress)
    except ChangeError as e:
        await app.bot.send_message(chat_id, f"⛔ {e}")
        return
    icon = {"done": "✅", "rolled_back": "↩️", "undone": "↩️"}.get(req.status, "❌")
    markup = (InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Hoàn tác", callback_data=f"undo|{_cb(rid)}")]])
              if req.status == "done" else None)
    await app.bot.send_message(chat_id, f"{icon} #{rid} {req.device}: {req.status}\n" + "\n".join(req.log)[-TG_LIMIT:],
                               reply_markup=markup)


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if allowed(update) and context.args:
        await _approve(update, context, context.args[0])


async def _approve(update: Update, context, rid: str) -> None:
    reply = update.effective_message
    if not can_approve(update):
        await reply.reply_text("⛔ Bạn không có quyền duyệt thay đổi (CHANGE_APPROVER_IDS).")
        return
    try:
        req = service.changes().get(rid)
    except ChangeError as e:
        await reply.reply_text(f"⛔ {e}")
        return
    if FOUR_EYES and req.requester.split()[0] == _who(update).split()[0]:
        await reply.reply_text("⛔ Chế độ 4 mắt: cần người khác duyệt yêu cầu của bạn.")
        return
    await run_change(context.application, update.effective_chat.id, rid, _who(update))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if allowed(update) and context.args:
        try:
            service.changes().cancel(context.args[0], _who(update))
            await update.message.reply_text(f"❌ Đã huỷ #{context.args[0]}")
        except ChangeError as e:
            await update.message.reply_text(f"⛔ {e}")


async def undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if allowed(update) and context.args:
        if not can_approve(update):
            await update.message.reply_text("⛔ Bạn không có quyền hoàn tác.")
            return
        await run_change(context.application, update.effective_chat.id, context.args[0], _who(update), undo=True)


async def list_changes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    reqs = sorted(service.changes().requests.values(), key=lambda r: r.created)[-15:]
    if not reqs:
        await update.message.reply_text("Chưa có yêu cầu thay đổi nào trong phiên bot này.")
        return
    rows = [f"#{r.id} {r.device:<14} {r.status:<11} {r.requester.split(' ', 1)[-1][:16]}  {r.commands[0][:30]}"
            for r in reqs]
    await reply_long(update.message, "\n".join(rows))


async def compliance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if allowed(update):
        await _run(update, "📋 Đang kiểm tuân thủ (đọc running-config từng thiết bị)...", service.compliance_check,
                   " ".join(context.args) or "all")


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if allowed(update):
        await _run(update, "💾 Đang backup và so với configs/...", service.backup, " ".join(context.args) or "all")


async def drift_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    if not context.args:
        await update.message.reply_text("Cú pháp: /drift Switch32")
        return
    await _run(update, "⏳ Đang so running-config với configs/...", service.drift_detail, context.args[0])


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not allowed(update):
        await q.answer("Không có quyền", show_alert=True)
        return
    action, _, ref = (q.data or "").partition("|")
    value = _CB.get(ref)
    if value is None:
        await q.answer("Nút đã hết hạn (bot vừa khởi động lại).", show_alert=True)
        return
    if action == "approve":
        await q.answer()
        await q.edit_message_reply_markup(None)        # chặn bấm Duyệt hai lần
        await _approve(update, context, value)
    elif action == "cancel":
        try:
            service.changes().cancel(value, _who(update))
            await q.answer("Đã huỷ")
            await q.edit_message_reply_markup(None)
        except ChangeError as e:
            await q.answer(str(e)[:190], show_alert=True)
    elif action == "undo":
        if not can_approve(update):
            await q.answer("Không có quyền hoàn tác", show_alert=True)
            return
        await q.answer()
        await q.edit_message_reply_markup(None)
        await run_change(context.application, update.effective_chat.id, value, _who(update), undo=True)
    elif action == "mute":
        context.application.bot_data["monitor"].mute(value, 3600)
        await q.answer("Đã tắt cảnh báo này 1 giờ")
        await q.message.reply_text(f"🔕 Tắt 1 giờ: {value}")
    elif action == "diag":
        await q.answer("Đang chẩn đoán...")
        res = await asyncio.to_thread(service.diagnose, value)
        await reply_long(q.message, str(res))


async def alert_loop(app: Application) -> None:
    monitor: AlertMonitor = app.bot_data["monitor"]
    while True:
        try:
            alerts = await asyncio.to_thread(monitor.poll)
        except Exception:
            logger.exception("Lỗi vòng cảnh báo")
            alerts = []
        for a in alerts:
            buttons = [InlineKeyboardButton(f"🩺 Chẩn đoán {d}", callback_data=f"diag|{_cb(d)}") for d in a.diagnose[:2]]
            if a.level != "recovery":
                buttons.append(InlineKeyboardButton("🔕 Tắt 1 giờ", callback_data=f"mute|{_cb(a.key)}"))
            markup = InlineKeyboardMarkup([buttons]) if buttons else None
            for chat in ALERT_CHATS:
                try:
                    await app.bot.send_message(chat, f"{a.icon} {a.text}", reply_markup=markup)
                except Exception:
                    logger.exception("Không gửi được cảnh báo tới %s", chat)
        await asyncio.sleep(ALERT_INTERVAL)


async def post_init(app: Application) -> None:
    app.bot_data["monitor"] = AlertMonitor(service.vmanage(), service.ryu(), STATE_FILE)
    if ALERT_ENABLED and ALERT_CHATS:
        app.bot_data["alert_task"] = asyncio.create_task(alert_loop(app))
        logger.info("🔔 Vòng cảnh báo chạy mỗi %d s, gửi tới %d chat", ALERT_INTERVAL, len(ALERT_CHATS))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(update):
        return
    from main import agent     # import muộn: lệnh trực tiếp vẫn chạy khi thiếu API_KEY LLM
    processing = await update.message.reply_text("⏳ Đang phân tích và kết nối thiết bị...")
    started = time.time()
    try:
        final = ""
        async for s in agent.astream({"messages": [("user", update.message.text)]},
                                     config={"recursion_limit": 25}, stream_mode="values"):
            m = s["messages"][-1]
            if getattr(m, "type", "") == "ai" and m.content:
                final = m.content if isinstance(m.content, str) else str(m.content)
        await processing.delete()
        await reply_long(update.message, final or "⚠️ Agent không trả lời văn bản.", pre=False)
        # yêu cầu thay đổi do agent đề xuất trong lượt này → hiện thẻ duyệt cho người dùng
        for req in service.changes().unannounced_since(started):
            req.origin_chat = update.effective_chat.id
            await send_card(update.message, req)
    except Exception as e:
        logger.exception("Lỗi agent")
        resp = getattr(e, "response", None)
        if resp is not None and getattr(resp, "status_code", None):
            try:
                body = resp.json()
                err = body.get("error", body) if isinstance(body, dict) else {}
                detail = (err.get("message", "") if isinstance(err, dict) else str(err))[:200]
            except ValueError:
                detail = resp.text[:150]
            hint = {401: "API_KEY sai hoặc đã thu hồi.",
                    402: "Tài khoản LLM hết số dư — dùng model :free hoặc nạp thêm.",
                    429: "Vượt giới hạn yêu cầu (gói free theo phút/ngày) — thử lại sau.",
                    400: "Kiểm LLM_MODEL trong .env.",
                    404: "Model không tồn tại — kiểm LLM_MODEL."}.get(resp.status_code, "")
            await processing.edit_text(f"❌ LLM trả lỗi {resp.status_code}: {detail}\n{hint}\n"
                                       "Các lệnh /show, /diag, /health vẫn dùng được không cần AI.")
        else:
            await processing.edit_text(f"❌ Lỗi hệ thống: {type(e).__name__}: {str(e)[:150]}")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Thiếu TELEGRAM_BOT_TOKEN trong .env")
        return
    if not ALLOWED:
        logger.warning("TELEGRAM_ALLOWED_CHAT_IDS rỗng — mọi chat đều bị từ chối. "
                       "Nhắn /start cho bot để biết chat_id của bạn rồi điền vào .env.")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    for name, fn in [("start", start), ("devices", devices), ("show", show), ("ping", ping), ("diag", diag),
                     ("alarms", alarms), ("health", health), ("sdn", sdn), ("flows", flows), ("dhcp", dhcp),
                     ("change", change), ("approve", approve), ("cancel", cancel), ("undo", undo),
                     ("changes", list_changes), ("compliance", compliance), ("backup", backup),
                     ("drift", drift_cmd)]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🚀 Campus NetOps Bot đã chạy (cho phép %d chat).", len(ALLOWED))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
