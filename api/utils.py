# api/utils.py
import requests  # <-- requests kutubxonasini ishlatamiz
from django.conf import settings
import logging

# import telegram # <-- Endi bu import kerak emas, olib tashlashingiz mumkin

logger = logging.getLogger(__name__)


def send_direct_telegram_notification(telegram_id: int, message_text: str) -> bool:
    """
    Berilgan telegram_id ga Telegram bot orqali sinxron ravishda xabar yuboradi.
    Xabar HTML formatida yuboriladi deb hisoblanadi.
    """
    bot_token = settings.TELEGRAM_BOT_TOKEN  # settings.py da TELEGRAM_BOT_TOKEN bo'lishi kerak
    if not bot_token:
        logger.error("Telegram Bot Token (TELEGRAM_BOT_TOKEN) settings.py da sozlanmagan!")
        return False

    send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': str(telegram_id),
        'text': message_text,
        'parse_mode': 'HTML'  # Yoki MarkdownV2, matnga qarab
    }

    try:
        response = requests.post(send_url, json=payload, timeout=10)  # 10 soniya timeout
        response.raise_for_status()  # HTTP xatolik bo'lsa (4xx, 5xx) exception ko'taradi
        response_data = response.json()

        if response_data.get('ok'):
            logger.info(f"Notification sent successfully to Telegram ID {telegram_id} via direct request.")
            return True
        else:
            error_code = response_data.get('error_code')
            description = response_data.get('description')
            logger.error(f"Telegram API error sending notification to {telegram_id}: [{error_code}] {description}")
            return False
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error sending Telegram notification to {telegram_id}.")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error sending Telegram notification to {telegram_id}: {e}", exc_info=True)
        return False
    except Exception as e:  # Boshqa kutilmagan xatolar
        logger.error(f"Unexpected error sending Telegram notification to {telegram_id}: {e}", exc_info=True)
        return False
