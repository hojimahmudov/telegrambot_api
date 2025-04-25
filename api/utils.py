# api/utils.py
import telegram  # python-telegram-bot kutubxonasi
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


def send_telegram_otp(telegram_id: int, otp_code: str):
    """Berilgan telegram_id ga OTP kodni Telegram bot orqali yuboradi."""
    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        logger.error("Telegram Bot Token sozlanmagan!")
        # Token bo'lmasa, sinxron xatolik qaytarish o'rniga False qaytarish
        # yoki productionda buni qat'iy tekshirish kerak
        return False

    message = f"Sizning tasdiqlash kodingiz: {otp_code}"

    try:
        # Bot obyektini yaratamiz
        # Eslatma: Har safar chaqirilganda yaratish optimal emas, lekin sodda
        # Asinxron yondashuvda boshqacha bo'ladi
        bot = telegram.Bot(token=bot_token)

        # Xabarni yuboramiz
        # Bu sinxron chaqiruv - production uchun asinxron qilish kerak!
        bot.send_message(chat_id=telegram_id, text=message)

        logger.info(f"{telegram_id} ga OTP kodi muvaffaqiyatli yuborildi.")
        return True
    except telegram.error.BadRequest as e:
        # Eng ko'p uchraydigan xato: Foydalanuvchi botni topa olmadi yoki bloklagan
        logger.error(f"{telegram_id} ga xabar yuborishda xatolik (BadRequest): {e}")
        return False
    except Exception as e:
        # Boshqa kutilmagan xatolar
        logger.error(f"{telegram_id} ga xabar yuborishda noma'lum xatolik: {e}", exc_info=True)
        return False

# Agar Eskiz uchun send_sms funksiyasi bo'lsa, uni olib tashlang yoki kommentga oling
