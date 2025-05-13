# bot/handlers/profile.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ..utils.helpers import get_user_lang
from ..utils.api_client import make_api_request

logger = logging.getLogger(__name__)

async def show_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """API dan foydalanuvchi profilini oladi va ko'rsatadi."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang_code = get_user_lang(context)

    loading_text = "Profil ma'lumotlari yuklanmoqda..." if lang_code == 'uz' else "Загрузка данных профиля..."
    sent_message = await context.bot.send_message(chat_id=chat_id, text=loading_text)

    profile_data_response = await make_api_request(context, 'GET', 'users/profile/', user_id)

    final_text = ""
    final_markup = None # Hozircha tugma qo'shmaymiz, keyinroq "Tahrirlash" qo'shish mumkin

    if profile_data_response and not profile_data_response.get('error'):
        profile_data = profile_data_response

        first_name = profile_data.get('first_name', '')
        last_name = profile_data.get('last_name', '')
        username = profile_data.get('username')
        phone_number = profile_data.get('phone_number', 'N/A')
        profile_lang_code = profile_data.get('language_code', lang_code) # DB dagi til

        if lang_code == 'uz':
            final_text = "👤 <b>Sizning Profilingiz:</b>\n\n"
            final_text += f"Ism: {first_name}\n"
            if last_name:
                final_text += f"Familiya: {last_name}\n"
            if username:
                final_text += f"Telegram username: @{username}\n"
            final_text += f"Telefon raqam: {phone_number}\n"
            final_text += f"Tanlangan til: {'O‘zbekcha' if profile_lang_code == 'uz' else 'Русский'}\n\n"
            final_text += "Tilni o'zgartirish uchun /start buyrug'ini qayta bering."
        else: # ru
            final_text = "👤 <b>Ваш Профиль:</b>\n\n"
            final_text += f"Имя: {first_name}\n"
            if last_name:
                final_text += f"Фамилия: {last_name}\n"
            if username:
                final_text += f"Telegram username: @{username}\n"
            final_text += f"Номер телефона: {phone_number}\n"
            final_text += f"Tanlangan til: {'O‘zbekcha' if profile_lang_code == 'uz' else 'Русский'}\n\n"
            final_text += "Для смены языка, отправьте команду /start снова."

        # Kelajakda "Tahrirlash" yoki "Tilni o'zgartirish" tugmalarini qo'shish mumkin
        # keyboard = [[InlineKeyboardButton("Tilni o'zgartirish", callback_data="change_lang_profile")]]
        # final_markup = InlineKeyboardMarkup(keyboard)

    elif profile_data_response and profile_data_response.get('status_code') == 401:
         final_text = "Profil ma'lumotlarini ko'rish uchun tizimga kiring (/start)." if lang_code == 'uz' else "Войдите в систему для просмотра профиля (/start)."
    else:
        error_detail = profile_data_response.get('detail', 'N/A') if profile_data_response else 'Server xatosi'
        final_text = f"Profil ma'lumotlarini yuklashda xatolik: {error_detail}" if lang_code == 'uz' else f"Ошибка загрузки профиля: {error_detail}"
        logger.error(f"Failed to fetch profile for user {user_id}: {error_detail}")

    # "Yuklanmoqda..." xabarini tahrirlaymiz
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=sent_message.message_id,
            text=final_text,
            reply_markup=final_markup, # Hozircha None
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error editing profile message: {e}")
        try: await context.bot.delete_message(chat_id=chat_id, message_id=sent_message.message_id)
        except: pass
        await context.bot.send_message(chat_id=chat_id, text=final_text, reply_markup=final_markup, parse_mode=ParseMode.HTML)