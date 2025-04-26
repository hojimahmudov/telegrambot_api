# bot/handlers/main_menu.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from ..config import MAIN_MENU
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
        reply_text = "Buyurtmalar tarixi..." if lang_code == 'uz' else "История заказов..."
        # TODO: Implement show_order_history function call here (from .orders)
        pass  # Hozircha placeholder
    elif message_text in ["📍 Filiallar", "📍 Филиалы"]:
        reply_text = "Filiallar ro'yxati..." if lang_code == 'uz' else "Список филиалов..."
        # TODO: Implement show_branch_list function call here (from ??? maybe common or menu_browse?)
        pass  # Hozircha placeholder
    elif message_text in ["👤 Profil", "👤 Профиль"]:
        reply_text = "Profil ma'lumotlari..." if lang_code == 'uz' else "Данные профиля..."
        # TODO: Implement show_profile function call here (from .profile)
        pass  # Hozircha placeholder
    elif message_text in ["⚙️ Sozlamalar", "⚙️ Настройки"]:
        reply_text = "Tilni o'zgartirish uchun /start buyrug'ini qayta bosing." \
            if lang_code == 'uz' else \
            "Чтобы изменить язык, нажмите /start снова."
    else:
        reply_text = "Noma'lum buyruq." if lang_code == 'uz' else "Неизвестная команда."

    # Agar reply_text bo'lsa (ya'ni, alohida funksiya chaqirilmagan bo'lsa) javob yuboramiz
    if reply_text:
        await update.message.reply_text(reply_text)

    return next_state
