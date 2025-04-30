# bot/handlers/common.py
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

# utils.helpers'dan import qilamiz
from ..utils.helpers import get_user_lang

logger = logging.getLogger(__name__)


async def debug_callback_in_state_5(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ASKING_DELIVERY_TYPE holatida HAR QANDAY callback queryni ushlaydi."""
    query = update.callback_query
    user_id = query.from_user.id if query.from_user else "Unknown"
    # Xabarni WARNING darajasida chiqaramiz, yaqqol ko'rinishi uchun
    logger.warning(
        f"DEBUG: Callback received in ASKING_DELIVERY_TYPE state! "
        f"Data: '{query.data}', Handler Pattern: '.*'. "
        f"Expected handler for '^checkout_set_' did NOT run."
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Joriy suhbatni bekor qiladi."""
    user = update.effective_user
    user_id = user.id if user else "Unknown User"
    lang_code = get_user_lang(context)
    logger.info(f"User {user_id} canceled the conversation.")

    # Kontekstdagi vaqtinchalik ma'lumotlarni tozalash
    keys_to_clear = ['registration_phone_number', 'current_category_id']
    for key in keys_to_clear:
        if key in context.user_data:
            del context.user_data[key]

    cancel_text = "Amal bekor qilindi. Boshlash uchun /start bosing." if lang_code == 'uz' else "Действие отменено. Нажмите /start, чтобы начать."
    if update.message:
        await update.message.reply_text(cancel_text, reply_markup=ReplyKeyboardRemove())
    elif update.callback_query:
        # Callbackdan keyin javob berish qiyinroq, yangi xabar yuboramiz
        await context.bot.send_message(chat_id=user_id, text=cancel_text, reply_markup=ReplyKeyboardRemove())

    return ConversationHandler.END
