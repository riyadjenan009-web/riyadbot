import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import firebase_admin
from firebase_admin import credentials, firestore

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_TOKEN")
COLLECTION = "riyad_aljinan_bot_groups"

groups = {}

# --------------------------
# Firebase Bağlantısı
# --------------------------
firebase_json = json.loads(os.getenv("FIREBASE_CREDENTIALS"))
cred = credentials.Certificate(firebase_json)
firebase_admin.initialize_app(cred)
db = firestore.client()

# --------------------------
# Dummy HTTP Server (Render port gereksinimi için)
# --------------------------
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, format, *args):
        pass

def run_server():
    port = int(os.getenv("PORT", 10000))
    HTTPServer(("0.0.0.0", port), DummyHandler).serve_forever()

# --------------------------
# Veri Kaydetme (Firestore)
# --------------------------
def save_group(chat_id):
    chat_id = str(chat_id)
    db.collection(COLLECTION).document(chat_id).set(groups[chat_id])

def load_state():
    global groups
    groups = {}
    try:
        docs = db.collection(COLLECTION).stream()
        for doc in docs:
            groups[doc.id] = doc.to_dict()
    except Exception as e:
        print(f"Firestore yükleme hatası: {e}")
        groups = {}

# --------------------------
# Helpers
# --------------------------
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        return True
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
    # style: 'primary' (أزرق), 'success' (أخضر), 'danger' (أحمر)
    # ملاحظة: الألوان تظهر فقط بنسخ تيليجرام بعد 9 فبراير 2026
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✋🏻 أود المشاركة", callback_data="join", style="primary"),
            InlineKeyboardButton("🎧 مستمعة", callback_data="listen", style="primary"),
        ],
        [
            InlineKeyboardButton("✅ أنهيت القراءة", callback_data="done", style="success"),
        ],
        [
            InlineKeyboardButton("⛔️ إيقاف الإعلان", callback_data="stop", style="danger"),
        ]
    ])

# --------------------------
# /start
# --------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        if update.message:
            try:
                await update.message.delete()
            except:
                pass
        return

    if update.message:
        try:
            await update.message.delete()
        except:
            pass

    chat_id = str(update.effective_chat.id)
    group = get_group(chat_id)

    # 🔵 إذا الجلسة نشطة → إرسال رسالة جديدة فورًا ثم حذف القديمة (بدون فجوة)
    if group["active"]:
        old_message_id = group["message_id"]

        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=build_text(group),
            reply_markup=build_keyboard(),
            parse_mode="Markdown"
        )
        group["message_id"] = msg.message_id

        if old_message_id:
            try:
                await context.bot.delete_message(chat_id, old_message_id)
            except:
                pass
        save_group(chat_id)
        return

    # 🔴 إذا الجلسة موقوفة → نبدأ جلسة جديدة نظيفة

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
    save_group(chat_id)

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
        save_group(chat_id)

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

    save_group(chat_id)

    try:
        await query.edit_message_text(
            build_text(group),
            reply_markup=build_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise

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
