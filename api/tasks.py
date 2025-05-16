# api/tasks.py
from celery import shared_task
from django.conf import settings
import requests
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)  # 3 marta qayta urinish, 1 daqiqa oraliq bilan
def send_otp_telegram_task(self, telegram_id: int, otp_code: str):
    """
    OTP kodni Telegram bot orqali asinxron ravishda yuboradi.
    Bu vazifa Celery worker tomonidan bajariladi.
    """
    bot_token = settings.TELEGRAM_BOT_TOKEN  # settings.py dan olamiz
    if not bot_token:
        logger.error("TASK ERROR: Telegram Bot Token sozlanmagan!")
        return False  # Yoki self.retry(exc=...)

    message = f"Sizning tasdiqlash kodingiz: {otp_code}"
    send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': str(telegram_id),
        'text': message,
        'parse_mode': 'HTML'
    }

    try:
        response = requests.post(send_url, json=payload, timeout=10)
        response.raise_for_status()  # HTTP xatolik bo'lsa exception
        response_data = response.json()

        if response_data.get('ok'):
            logger.info(f"TASK SUCCESS: OTP {otp_code} to {telegram_id} sent successfully via Telegram.")
            return True
        else:
            error_code = response_data.get('error_code')
            description = response_data.get('description')
            logger.error(f"TASK ERROR: Telegram API xatoligi [{error_code}] {description} for {telegram_id}")
            # Qayta urinish uchun exception chaqirish mumkin
            # self.retry(exc=Exception(f"Telegram API Error: {description}"))
            return False
    except requests.exceptions.RequestException as exc:
        logger.error(f"TASK ERROR: Network xatoligi OTP yuborishda {telegram_id}: {exc}")
        self.retry(exc=exc)  # Celery ga qayta urinishni aytamiz
        return False  # Bu qatorga yetmasligi kerak, lekin ehtiyot shart
    except Exception as exc:  # Boshqa kutilmagan xatolar
        logger.error(f"TASK ERROR: Noma'lum xatolik OTP yuborishda {telegram_id}: {exc}", exc_info=True)
        self.retry(exc=exc)
        return False
