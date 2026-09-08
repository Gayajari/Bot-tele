import os
import requests
import telebot
from telebot import types
from flask import Flask, request

# ================== KONFIGURASI ==================
BOT_TOKEN = os.environ.get("BOT_TOKEN")             # diisi lewat Environment Variables di Vercel

PREVIEW_LINK = os.environ.get("PREVIEW_LINK", "https://link-website-atau-beli-kamu.com")

# Daftar grup TIDAK di-hardcode di sini - diambil dari tabel Supabase "active_groups".
# Kalau ada grup kena blokir, cukup edit tabel di Supabase (tanpa redeploy Vercel).
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
# ===================================================

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)


def ambil_grup_aktif():
    """Ambil daftar grup yang wajib di-join, langsung dari Supabase."""
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/active_groups?is_active=eq.true&select=group_id,invite_link,label",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
            },
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()  # [{group_id, invite_link, label}, ...]
    except Exception as e:
        print(f"Gagal ambil daftar grup dari Supabase: {e}")
        return []


def is_member(user_id, chat_id):
    try:
        status = bot.get_chat_member(chat_id, user_id).status
        return status in ("member", "administrator", "creator")
    except Exception as e:
        # Kalau grup sudah dihapus/bot di-kick dari grup itu, anggap saja lolos
        # untuk grup ini supaya user tidak "terjebak" gara-gara 1 grup mati.
        print(f"Cek member gagal untuk grup {chat_id} (mungkin grup sudah tidak aktif): {e}")
        return True


def sudah_join_semua(user_id, groups):
    return all(is_member(user_id, g["group_id"]) for g in groups)


def kirim_prompt_join(chat_id, groups):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for g in groups:
        markup.add(types.InlineKeyboardButton(f"📌 Gabung {g['label']}", url=g["invite_link"]))
    markup.add(types.InlineKeyboardButton("✅ Sudah Gabung, Cek Lagi", callback_data="cek_member"))
    bot.send_message(
        chat_id,
        f"Untuk lihat preview & link, gabung dulu ke *{len(groups)} grup* di bawah ini ya:",
        reply_markup=markup,
        parse_mode="Markdown",
    )


@bot.message_handler(commands=["start"])
def start(message):
    groups = ambil_grup_aktif()
    if not groups:
        bot.send_message(message.chat.id, "Lagi ada gangguan, coba lagi sebentar ya.")
        return
    if sudah_join_semua(message.from_user.id, groups):
        bot.send_message(
            message.chat.id,
            f"Kamu sudah join semua grup \u2705\nIni link kamu:\n{PREVIEW_LINK}",
        )
    else:
        kirim_prompt_join(message.chat.id, groups)


@bot.callback_query_handler(func=lambda call: call.data == "cek_member")
def recheck(call):
    groups = ambil_grup_aktif()
    if not groups:
        bot.answer_callback_query(call.id, "Lagi ada gangguan, coba lagi sebentar ya.", show_alert=True)
        return
    if sudah_join_semua(call.from_user.id, groups):
        bot.send_message(
            call.message.chat.id,
            f"Mantap, kamu sudah join semua grup \u2705\nIni link kamu:\n{PREVIEW_LINK}",
        )
        bot.answer_callback_query(call.id)
    else:
        bot.answer_callback_query(
            call.id,
            "Kamu belum join semua grup, join dulu lalu tekan tombol ini lagi ya.",
            show_alert=True,
        )


# ---- Endpoint yang dipanggil Telegram tiap ada update ----
@app.route("/api/bot", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200


# ---- Endpoint bantu buat set webhook sekali aja (buka lewat browser) ----
@app.route("/api/bot", methods=["GET"])
def set_webhook():
    vercel_url = os.environ.get("VERCEL_URL")
    if not vercel_url:
        return "VERCEL_URL env tidak ditemukan", 500
    webhook_url = f"https://{vercel_url}/api/bot"
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    return f"Webhook diset ke: {webhook_url}", 200
