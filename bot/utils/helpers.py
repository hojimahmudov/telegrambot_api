# bot/utils/helpers.py
import logging
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def get_user_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Foydalanuvchi kontekstidan til kodini oladi yoki standart 'uz' qaytaradi."""
    return context.user_data.get('language_code', 'uz')


# --- Token Saqlash (Placeholder - XAVFSIZ EMAS!) ---
# Production uchun buni DB yoki xavfsizroq joyga o'tkazing!
# Persistence ishlatilganda bularni context.user_data orqali boshqarsa ham bo'ladi

async def get_user_token_data(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> dict | None:
    if context.application.persistence:
        user_persist_data = await context.application.persistence.get_user_data()
        return user_persist_data.get(user_id, {}).get('tokens')
    else:
        return context.user_data.get('tokens')  # Agar persistence yo'q bo'lsa


async def store_user_token_data(context: ContextTypes.DEFAULT_TYPE, user_id: int, access: str, refresh: str):
    token_data = {'access': access, 'refresh': refresh}
    context.user_data['tokens'] = token_data
    if context.application.persistence:
        await context.application.persistence.update_user_data(user_id=user_id, data=context.user_data)
    logger.info(f"Tokens stored in context for user {user_id}")


async def clear_user_token_data(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    if 'tokens' in context.user_data:
        del context.user_data['tokens']
    if context.application.persistence:
        await context.application.persistence.update_user_data(user_id=user_id, data=context.user_data)
    logger.info(f"Tokens cleared from context for user {user_id}")

# Tilni DBda yangilash funksiyasi (make_api_request'ni talab qiladi)
# Buni api_client.py ga ko'chirish yoki shu yerda qoldirish mumkin
# async def update_language_in_db(...): ... # Buni api_client.py ga ko'chirgan ma'qulroq, chunki u API call qiladi
