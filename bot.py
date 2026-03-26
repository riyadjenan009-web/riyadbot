import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_TOKEN")
STATE_FILE = "state.json"

groups = {}

# --------------------------
# Dummy HTTP Server (Railway)
# --------------------------
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_server():
    HTTPServer(("0.0.0.0", 1551), DummyHandler).serve_forever()

# --------------------------
# State Persistence
# --------------------------
def save_state():
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(groups, f, ensure_ascii=False)

def load_state():
    global groups
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            groups = json.load(f)
    except:
        groups = {}

# --------------------------
# Helpers
# --------------------------
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    return any(a.user.id == user_id for a in admins)

# 🔹 نجبر الاسم يكون بمحاذاة اليمين دائمًا
def rtl(text: str) -> str:
    return "\u200f" + text

def get_group(chat_id):
    chat_id = str(chat_id)
    if chat_id not in groups:
        groups[chat_id] = {
            "participants": {},
            "listeners": [],
            "active": False,
            "message_id": None
        }
    return groups[chat_id]

# --------------------------
# UI
# --------------------------
def build_text(group):
    text = "*🪻 أكاديمية رياض الجنان 🪻*\n"
    text += "*🪻 بإدارة نجلاء درابسة 🪻*\n\n"

    text += "*🪻 المشاركات في الحلقة:*\n"
    if group["participants"]:
        for i, (name, done) in enumerate(group["participants"].items(), start=1):
            mark = " ✅" if done else ""
            text += f"{i}. {rtl(name)}{mark}\n"
    else:
        text += "لا توجد مشاركات حتى الآن 😔\n"

    text += "\n*🪻 المستمعات:*\n"
    if group["listeners"]:
        for i, name in enumerate(group["listeners"], start=1):
            text += f"{i}. {rtl(name)}\n"
    else:
        text += "لا توجد مستمعات حتى الآن 🎧\n"

    text += (
    
        "*اللهم اجعل القرآن ربيع قلوبنا ونور صدورنا 🤲🏻*\n\n"
    )

    if group["active"]:
        text += "👇 اختاري حالتك من الأزرار بالأسفل"
    else:
        text += "🪻 انتهت الحلقة 🪻"

    return text

def build_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✋🏻 أود المشاركة", callback_data="join"),
            InlineKeyboardButton("🎧 مستمعة", callback_data="listen"),
        ],
        [
            InlineKeyboardButton("✅ أنهيت القراءة", callback_data="done"),
        ],
        [
            InlineKeyboardButton("⛔️ إيقاف الإعلان", callback_data="stop"),
        ]
    ])

# --------------------------
# /start
# --------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message:
        try:
            await update.message.delete()
        except:
            pass

    if not await is_admin(update, context):
        return

    chat_id = str(update.effective_chat.id)
    group = get_group(chat_id)

    # 🔵 إذا الجلسة نشطة → حذف الرسالة القديمة وإعادة إرسالها بنفس الأسماء
    if group["active"]:

        if group["message_id"]:
            try:
                await context.bot.delete_message(chat_id, group["message_id"])
            except:
                pass

        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=build_text(group),
            reply_markup=build_keyboard(),
            parse_mode="Markdown"
        )

        group["message_id"] = msg.message_id
        save_state()
        return

    # 🔴 إذا الجلسة موقوفة → لا نحذف الرسالة القديمة، نبدأ جلسة جديدة نظيفة

    group["participants"] = {}
    group["listeners"] = []
    group["active"] = True

    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=build_text(group),
        reply_markup=build_keyboard(),
        parse_mode="Markdown"
    )

    group["message_id"] = msg.message_id
    save_state()

# --------------------------
# Buttons
# --------------------------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = str(query.message.chat.id)
    group = get_group(chat_id)
    name = query.from_user.full_name

    if query.data == "stop":
        if not await is_admin(update, context):
            return

        group["active"] = False
        save_state()

        await query.edit_message_text(
            build_text(group),
            reply_markup=None,
            parse_mode="Markdown"
        )
        return

    if not group["active"]:
        await query.answer("🪻 انتهت الحلقة")
        return

    if query.data == "join":
        if name in group["participants"]:
            await query.answer("أنتِ مشاركة بالفعل 🪻")
            return

        if name in group["listeners"]:
            group["listeners"].remove(name)

        group["participants"][name] = False
        await query.answer("🪻 نيتك طيبة، ربي يبارك فيكِ")

    elif query.data == "listen":
        if name in group["participants"]:
            await query.answer("أنتِ مسجلة كمشاركة")
            return

        if name not in group["listeners"]:
            group["listeners"].append(name)
            await query.answer("🪻 نفعكِ الله بالقرآن")

    elif query.data == "done":
        if name not in group["participants"]:
            await query.answer("لم يتم تسجيلكِ كمشاركة")
            return

        if group["participants"][name]:
            await query.answer("تم تسجيل الانتهاء مسبقًا")
            return

        group["participants"][name] = True
        await query.answer("🪻 ما شاء الله، بارك الله فيكِ")

    save_state()

    await query.edit_message_text(
        build_text(group),
        reply_markup=build_keyboard(),
        parse_mode="Markdown"
    )

# --------------------------
# Main
# --------------------------
def main():
    load_state()
    threading.Thread(target=run_server, daemon=True).start()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    app.run_polling()

if __name__ == "__main__":
    main()
