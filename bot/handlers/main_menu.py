# bot/handlers/main_menu.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from .branch import show_branch_list_menu
from .order import show_order_history
from .profile import show_user_profile
from .promotions import show_promotions_list
from ..config import MAIN_MENU, SELECTING_LANG
from ..keyboards import get_language_keyboard
from ..utils.helpers import get_user_lang
from ..utils.api_client import make_api_request  # API client kerak
from .menu_browse import show_category_list
from .cart import show_cart

logger = logging.getLogger(__name__)


async def main_menu_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Asosiy menyu holatidagi matnli xabarlarni (tugmalarni) boshqaradi."""
    user = update.effective_user
    user_id = user.id if user else "Unknown"
    lang_code = get_user_lang(context)
    message_text = update.message.text
    logger.info(f"Received main menu command '{message_text}' from user {user_id}")

    reply_text = ""
    next_state = MAIN_MENU  # Standart holatda shu menyuda qolamiz

    # Qaysi menyu tugmasi bosilganini tekshiramiz
    if message_text in ["🍽️ Menyu", "🍽️ Меню"]:
        await show_category_list(update, context)  # Kategoriyalarni ko'rsatish funksiyasini chaqiramiz
        return next_state  # Xabar show_category_list ichida yuboriladi

    elif message_text in ["🛒 Savat", "🛒 Корзина"]:

        loading_text = "Savat yuklanmoqda..." if lang_code == 'uz' else "Загрузка корзины..."

        await update.message.reply_text(loading_text)

        cart_response = await make_api_request(context, 'GET', 'cart/', user_id)

        if cart_response and not cart_response.get('error'):

            await show_cart(update, context, cart_response)  # Call show_cart

        elif cart_response and cart_response.get('status_code') == 401:

            pass  # Error handled in make_api_request

        else:

            error_detail = cart_response.get('detail', 'N/A') if cart_response else 'N/A'

            reply_text = f"Savatni olib bo'lmadi: {error_detail}" if lang_code == 'uz' else f"Не удалось получить корзину: {error_detail}"

            await update.message.reply_text(reply_text)

    elif message_text in ["📋 Buyurtmalarim", "📋 Мои заказы"]:
        loading_text = "Buyurtmalar tarixi yuklanmoqda..." if lang_code == 'uz' else "Загрузка истории заказов..."
        await update.message.reply_text(loading_text)
        history_response = await make_api_request(context, 'GET', 'orders/history/', user_id)
        if history_response and not history_response.get('error'):
            await show_order_history(update, context, history_response)  # <-- Yangi funksiyani chaqiramiz
        elif history_response and history_response.get('status_code') == 401:
            pass  # Xatolik make_api_request ichida hal qilinadi
        else:
            error_detail = history_response.get('detail', 'N/A') if history_response else 'N/A'
            reply_text = f"Buyurtmalar tarixini olib bo'lmadi: {error_detail}" if lang_code == 'uz' else f"Не удалось получить историю заказов: {error_detail}"
            await update.message.reply_text(reply_text)
        return next_state  # MAIN_MENU da qolamiz
    elif message_text in ["📍 Filiallar", "📍 Филиалы"]:
        await show_branch_list_menu(update, context)  # <-- Yangi funksiyani chaqiramiz
        return next_state  # MAIN_MENU da qolamiz

    elif message_text in ["👤 Profil", "👤 Профиль"]:
        reply_text = "Profil ma'lumotlari..." if lang_code == 'uz' else "Данные профиля..."
        await show_user_profile(update, context)  # <-- Yangi funksiyani chaqiramiz
        return next_state  # MAIN_MENU da qolamiz

    elif message_text in ["🎁 Aksiyalar", "🎁 Акции"]:
        await show_promotions_list(update, context)  # <-- Yangi funksiyani chaqiramiz
        return next_state

    elif message_text in ["⚙️ Sozlamalar", "⚙️ Настройки"]:
        settings_text = "Tilni tanlang:" if lang_code == 'uz' else "Выберите язык:"
        reply_markup = get_language_keyboard()  # Til tanlash klaviaturasini olamiz
        await update.message.reply_text(settings_text, reply_markup=reply_markup)
        next_state = SELECTING_LANG

    else:
        reply_text = "Noma'lum buyruq." if lang_code == 'uz' else "Неизвестная команда."

    # Agar reply_text bo'lsa (ya'ni, alohida funksiya chaqirilmagan bo'lsa) javob yuboramiz
    if reply_text:
        await update.message.reply_text(reply_text)

    return next_state
