# bot/config.py
import os
from dotenv import load_dotenv

# .env faylini o'qish uchun loyiha root papkasini topish
# Bu bot/bot.py dan chaqirilganda to'g'ri ishlashi kerak
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')  # bot dan ikki papka yuqoridagi .env
load_dotenv(dotenv_path=dotenv_path)

# --- Sozlamalar ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Iltimos, .env faylida TELEGRAM_BOT_TOKEN ni o'rnating.")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api/v1/")

# --- Holatlar (States) ---
SELECTING_LANG, AUTH_CHECK, WAITING_PHONE, WAITING_OTP, MAIN_MENU, SELECTING_PRODUCT, VIEWING_PRODUCT = map(chr,
                                                                                                            range(7))
# Agar kerak bo'lsa, boshqa holatlarni qo'shish mumkin, masalan CHECKOUT_STATE

# --- Boshqa konstantalar (agar kerak bo'lsa) ---
# Masalan: DEFAULT_LANG = 'uz'
