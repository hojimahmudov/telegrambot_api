# bot/handlers/common.py
import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

# utils.helpers'dan import qilamiz
from ..utils.helpers import get_user_lang

logger = logging.getLogger(__name__)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Joriy suhbatni bekor qiladi va asosiy menyuga qaytaradi (yoki shunchaki tugatadi)."""
    user = update.effective_user
    user_id = user.id if user else "Unknown User"
    lang_code = get_user_lang(context)
    logger.info(f"User {user_id} canceled the conversation.")

    # Checkout yoki boshqa jarayonlarga oid vaqtinchalik ma'lumotlarni tozalash
    keys_to_clear = ['registration_phone_number', 'current_category_id',
                     'checkout_delivery_type', 'checkout_pickup_branch_id',
                     'checkout_latitude', 'checkout_longitude',
                     'checkout_payment_type', 'checkout_notes']
    for key in keys_to_clear:
        if key in context.user_data:
            try:
                del context.user_data[key]
                logger.debug(f"Removed '{key}' from user_data for user {user_id}")
            except KeyError:
                pass  # Agar allaqachon yo'q bo'lsa

    cancel_text = "Amal bekor qilindi." if lang_code == 'uz' else "Действие отменено."

    # Callback query bo'lsa, eski xabarni tahrirlashga harakat qilamiz
    if update.callback_query:
        try:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(cancel_text)
        except Exception as e:
            logger.warning(f"Could not edit message on cancel callback: {e}")
            # Fallback: Send new message
            await context.bot.send_message(chat_id=user_id, text=cancel_text, reply_markup=ReplyKeyboardRemove())
    # Agar /cancel buyrug'i bo'lsa
    elif update.message:
        await update.message.reply_text(cancel_text, reply_markup=ReplyKeyboardRemove())

    # Asosiy menyuga qaytarish uchun MAIN_MENU ni qaytarish ham mumkin,
    # lekin END suhbatni to'liq tugatadi, keyingi /start yangi boshlaydi.
    from bot.config import MAIN_MENU
    return MAIN_MENU
