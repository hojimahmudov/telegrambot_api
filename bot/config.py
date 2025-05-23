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
(SELECTING_LANG, AUTH_CHECK,
 CHOOSING_PHONE_METHOD,
 WAITING_PHONE,
 WAITING_MANUAL_PHONE, MAIN_MENU,
 ASKING_DELIVERY_TYPE, ASKING_BRANCH, ASKING_LOCATION, CONFIRMING_LOCATION, SELECTING_ADDRESS_OR_NEW,
 ASKING_SAVE_NEW_ADDRESS,
 ENTERING_ADDRESS_NAME, ASKING_PAYMENT,
 ASKING_NOTES
 ) = range(15)
# Agar kerak bo'lsa, boshqa holatlarni qo'shish mumkin, masalan CHECKOUT_STATE

# --- Boshqa konstantalar (agar kerak bo'lsa) ---
# Masalan: DEFAULT_LANG = 'uz'
