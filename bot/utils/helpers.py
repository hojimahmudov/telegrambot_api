# bot/utils/helpers.py
import logging
from telegram.ext import ContextTypes

from bot.utils.db_utils import get_user_session_data, save_user_session_data

logger = logging.getLogger(__name__)


def get_user_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Til kodini oladi: avval user_data dan, keyin DB dan, topilmasa 'uz'."""
    # user_id ni olishga harakat qilamiz
    user_id = None
    if context.effective_user:  # Bu har doim Update ichida bo'ladi
        user_id = context.effective_user.id
    elif context.user_data and '_effective_user_id' in context.user_data:  # Ba'zi eski holatlar uchun
        user_id = context.user_data['_effective_user_id']

    # 1. Avval user_data (joriy sessiya) dan qidiramiz
    lang_code = context.user_data.get('language_code')
    if lang_code:
        return lang_code

    # 2. Agar user_data da bo'lmasa va user_id mavjud bo'lsa, DB dan qidiramiz
    if user_id:
        session = get_user_session_data(user_id)  # Bu db_utils dan keladi
        if session and session.get('lang'):
            context.user_data['language_code'] = session['lang']  # user_data ga keshlash
            return session['lang']

    return 'uz'  # Standart til


# --- Token Saqlash (Placeholder - XAVFSIZ EMAS!) ---
# Production uchun buni DB yoki xavfsizroq joyga o'tkazing!
# Persistence ishlatilganda bularni context.user_data orqali boshqarsa ham bo'ladi

async def get_user_token_data(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> dict | None:
    """Token ma'lumotlarini DB dan oladi."""
    session = get_user_session_data(user_id)
    if session and session.get('access') and session.get('refresh'):
        # context.user_data['tokens'] ga qayta yozish shart emas, make_api_request o'zi oladi
        return {'access': session['access'], 'refresh': session['refresh']}
    return None


async def store_user_token_data(context: ContextTypes.DEFAULT_TYPE, user_id: int, access: str, refresh: str):
    """Tokenlarni va joriy tilni DB ga saqlaydi."""
    # Joriy tilni user_data dan olamiz (set_language_callback uni o'rnatgan bo'lishi kerak)
    current_lang = context.user_data.get('language_code', 'uz')
    save_user_session_data(user_id, access_token=access, refresh_token=refresh, language_code=current_lang)
    logger.info(f"Tokens and lang '{current_lang}' stored in DB for user {user_id}")


async def clear_user_token_data(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Tokenlarni DB dan o'chiradi (tilni saqlab qolishi mumkin)."""
    # Faqat tokenlarni None qilish yoki butun yozuvni o'chirish
    # Hozircha faqat tokenlarni None qilamiz:
    save_user_session_data(user_id, access_token="", refresh_token="")  # Bo'sh satr yoki None
    # Yoki butunlay o'chirish uchun:
    # clear_user_session_data(user_id) # Bu tilni ham o'chiradi

    # context.user_data dan ham o'chiramiz
    if 'tokens' in context.user_data:
        del context.user_data['tokens']
    logger.info(f"Tokens cleared from DB (set to empty) for user {user_id}")


async def save_user_language_preference(user_id: int, lang_code: str):
    """Foydalanuvchining faqat til sozlamasini DB ga saqlaydi."""
    save_user_session_data(telegram_id=user_id, language_code=lang_code)
    logger.info(f"Language preference '{lang_code}' saved to DB for user {user_id}")
# Tilni DBda yangilash funksiyasi (make_api_request'ni talab qiladi)
# Buni api_client.py ga ko'chirish yoki shu yerda qoldirish mumkin
# async def update_language_in_db(...): ... # Buni api_client.py ga ko'chirgan ma'qulroq, chunki u API call qiladi
