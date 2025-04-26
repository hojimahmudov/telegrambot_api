# bot/handlers/menu_browse.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

# Loyihadagi boshqa modullardan importlar
from ..utils.helpers import get_user_lang
from ..utils.api_client import make_api_request

# Holatlar kerak bo'lishi mumkin (agar menyudan chiqilsa)
# from ..config import MAIN_MENU

logger = logging.getLogger(__name__)


async def show_category_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kategoriyalarni oladi va inline tugmalar bilan xabar yuboradi."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang_code = get_user_lang(context)

    loading_text = "Kategoriyalar yuklanmoqda..." if lang_code == 'uz' else "Загрузка категорий..."
    sent_message = await context.bot.send_message(chat_id=chat_id, text=loading_text)

    categories_response = await make_api_request(context, 'GET', 'categories/', user_id)  # Token shart emas bunga
    final_text = ""
    final_markup = None

    if categories_response and not categories_response.get('error'):
        categories = categories_response.get('results', [])
        if categories:
            keyboard = [[InlineKeyboardButton(c.get('name', 'N/A'), callback_data=f"cat_{c.get('id')}")] for c in
                        categories]
            final_markup = InlineKeyboardMarkup(keyboard)
            final_text = "Kategoriyalardan birini tanlang:" if lang_code == 'uz' else "Выберите одну из категорий:"
        else:
            final_text = "Kategoriyalar topilmadi." if lang_code == 'uz' else "Категории не найдены."
    else:
        error_detail = categories_response.get('detail',
                                               'Noma\'lum xatolik') if categories_response else 'Server bilan bog\'lanish xatosi'
        final_text = f"Kategoriyalarni olib bo'lmadi: {error_detail}" if lang_code == 'uz' else f"Не удалось получить категории: {error_detail}"

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=sent_message.message_id,
            text=final_text, reply_markup=final_markup
        )
    except Exception as e:
        logger.error(f"Error editing category list message: {e}")
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=sent_message.message_id)
        except:
            pass
        await context.bot.send_message(chat_id=chat_id, text=final_text, reply_markup=final_markup)


async def show_product_list(update: Update, context: ContextTypes.DEFAULT_TYPE, category_id: int):
    """Berilgan kategoriya uchun mahsulotlarni rasm+tugma ko'rinishida chiqaradi."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang_code = get_user_lang(context)
    context.user_data['current_category_id'] = category_id

    loading_text = "Mahsulotlar ro'yxati yuklanmoqda..." if lang_code == 'uz' else "Загрузка списка продуктов..."
    sent_message = await context.bot.send_message(chat_id=chat_id, text=loading_text)

    products_response = await make_api_request(context, 'GET', f'products/?category_id={category_id}',
                                               user_id)  # Token shart emas

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=sent_message.message_id)
    except Exception:
        pass

    if products_response and not products_response.get('error'):
        products = products_response.get('results', [])
        category_info = products[0].get('category', {}) if products else {}
        category_name = category_info.get('name', 'Kategoriya')
        category_image_url = category_info.get('image_url')
        keyboard = []
        caption = f"<b>{category_name}</b>\n\nMahsulotni tanlang:" if lang_code == 'uz' else f"<b>{category_name}</b>\n\nВыберите продукт:"

        if products:
            for product in products:
                button = InlineKeyboardButton(product.get('name', 'Nomsiz'), callback_data=f"prod_{product.get('id')}")
                keyboard.append([button])
        else:
            caption = "Bu kategoriyada mahsulotlar topilmadi." if lang_code == 'uz' else "В этой категории товары не найдены."

        back_button_text = "< Ortga" if lang_code == 'uz' else "< Назад"
        keyboard.append([InlineKeyboardButton(back_button_text, callback_data="back_to_categories")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        photo_url = category_image_url

        if photo_url:
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=photo_url, caption=caption,
                                             reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Failed to send category photo {photo_url}: {e}")
                await context.bot.send_message(chat_id=chat_id, text=caption, reply_markup=reply_markup,
                                               parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=chat_id, text=caption, reply_markup=reply_markup,
                                           parse_mode=ParseMode.HTML)
    else:
        error_detail = products_response.get('detail', 'N/A') if products_response else 'N/A'
        reply_text = f"Mahsulotlarni olib bo'lmadi: {error_detail}" if lang_code == 'uz' else f"Не удалось получить товары: {error_detail}"
        await context.bot.send_message(chat_id=chat_id, text=reply_text)
