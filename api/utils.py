# api/utils.py
import requests  # <-- requests kutubxonasini ishlatamiz
from django.conf import settings
import logging

# import telegram # <-- Endi bu import kerak emas, olib tashlashingiz mumkin

logger = logging.getLogger(__name__)


def send_telegram_otp(telegram_id: int, otp_code: str):
    """Berilgan telegram_id ga OTP kodni Telegram bot API orqali requests yordamida yuboradi."""
    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        logger.error("Telegram Bot Token sozlanmagan!")
        return False

    message = f"Sizning tasdiqlash kodingiz: {otp_code}"
    # Telegram Bot API sendMessage endpoint URL manzili
    send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    # Yuboriladigan ma'lumotlar (payload)
    payload = {
        'chat_id': str(telegram_id),  # chat_id string bo'lishi kerak odatda
        'text': message,
        'parse_mode': 'HTML'  # Matnni formatlash uchun (ixtiyoriy)
    }

    try:
        # POST so'rovini yuboramiz
        response = requests.post(send_url, json=payload, timeout=10)  # Timeout qo'shish yaxshi amaliyot
        response.raise_for_status()  # HTTP xatolik bo'lsa (4xx, 5xx) exception ko'taradi

        response_data = response.json()  # Javobni JSON sifatida olamiz
        # Telegram API javobini tekshiramiz
        if response_data.get('ok'):
            logger.info(f"{telegram_id} ga OTP kodi muvaffaqiyatli yuborildi.")
            return True
        else:
            # Agar Telegram API 'ok: false' qaytarsa
            error_code = response_data.get('error_code')
            description = response_data.get('description')
            logger.error(f"{telegram_id} ga xabar yuborishda Telegram API xatoligi: [{error_code}] {description}")
            return False

    except requests.exceptions.Timeout:
        logger.error(f"{telegram_id} ga xabar yuborishda Timeout xatoligi.")
        return False
    except requests.exceptions.RequestException as e:
        # Boshqa network xatoliklar (ulanish, DNS va h.k.)
        logger.error(f"{telegram_id} ga xabar yuborishda network xatoligi: {e}", exc_info=True)
        return False
    except Exception as e:
        # Boshqa kutilmagan xatolar (masalan, JSON parse xatosi)
        logger.error(f"{telegram_id} ga xabar yuborishda noma'lum xatolik: {e}", exc_info=True)
        return False
