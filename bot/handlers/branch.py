# bot/handlers/branch.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ..utils.helpers import get_user_lang
from ..utils.api_client import make_api_request

logger = logging.getLogger(__name__)


async def show_branch_list_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """API dan filiallar ro'yxatini oladi va foydalanuvchiga ko'rsatadi."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang_code = get_user_lang(context)

    # Message yuborish/tahrirlash uchun
    message = update.message  # Agar menyu tugmasi bosilsa
    query = update.callback_query  # Agar callback (masalan, ortga) orqali kelinsa

    loading_text = "Filiallar yuklanmoqda..." if lang_code == 'uz' else "Загрузка филиалов..."
    sent_message = None
    if query:
        try:
            await query.answer()
            await query.edit_message_text(loading_text)
            sent_message = query.message  # Tahrirlanadigan xabar
        except Exception as e:
            logger.warning(f"Could not edit message for branch list loading: {e}")
            sent_message = await context.bot.send_message(chat_id=chat_id, text=loading_text)
    elif message:
        sent_message = await message.reply_text(loading_text)

    # Filiallar ro'yxatini API dan olamiz (bu endpoint token talab qilmasligi mumkin)
    branches_response = await make_api_request(context, 'GET', 'branches/', user_id)

    final_text = ""
    final_markup = None
    keyboard = []

    if branches_response and not branches_response.get('error'):
        branches = branches_response.get('results', [])
        if branches:
            final_text = "📍 <b>Bizning Filiallarimiz:</b>\n\n" if lang_code == 'uz' else "📍 <b>Наши Филиалы:</b>\n\n"
            for branch in branches:
                branch_name = branch.get('name', 'N/A')
                branch_address = branch.get('address', 'N/A')
                branch_id = branch.get('id')
                is_open = branch.get('is_open', False)  # API dan kelgan status
                status_text = "(Ochiq ✅)" if is_open else "(Yopiq ❌)"
                if lang_code == 'ru':
                    status_text = "(Открыто ✅)" if is_open else "(Закрыто ❌)"

                final_text += f"<b>{branch_name}</b> {status_text}\n"
                final_text += f"<pre>{branch_address}</pre>\n"
                # Har bir filial uchun "Xaritada ko'rish" tugmasi
                map_button_text = "🗺️ Xaritada" if lang_code == 'uz' else "🗺️ На карте"
                keyboard.append([
                    InlineKeyboardButton(f"{map_button_text} ({branch_name[:15]}...)",
                                         callback_data=f"branch_loc_{branch_id}")
                ])
                final_text += "--------------------\n"
            final_markup = InlineKeyboardMarkup(keyboard)
        else:
            final_text = "Hozircha filiallar haqida ma'lumot yo'q." if lang_code == 'uz' else "Информации о филиалах пока нет."
    else:
        error_detail = branches_response.get('detail', 'N/A') if branches_response else 'Server xatosi'
        final_text = f"Filiallarni yuklashda xatolik: {error_detail}" if lang_code == 'uz' else f"Ошибка загрузки филиалов: {error_detail}"
        logger.error(f"Failed to fetch branches for menu: {error_detail}")

    # Xabarni tahrirlaymiz yoki yangisini yuboramiz
    try:
        if sent_message:  # Agar "Yuklanmoqda" xabari yuborilgan bo'lsa
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=sent_message.message_id,
                text=final_text,
                reply_markup=final_markup,
                parse_mode=ParseMode.HTML
            )
        # Agar callbackdan kelgan bo'lsa va edit qilingan bo'lsa (loading_text)
        elif query and query.message:
            await query.edit_message_text(
                text=final_text,
                reply_markup=final_markup,
                parse_mode=ParseMode.HTML
            )

    except Exception as e:
        logger.error(f"Error editing/sending branch list message: {e}")
        # Fallback to sending a new message if editing failed
        await context.bot.send_message(chat_id=chat_id, text=final_text, reply_markup=final_markup,
                                       parse_mode=ParseMode.HTML)
