# bot/bot.py (MINIMAL TEST KODI)
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, TypeHandler, filters, PicklePersistence
)

# Faqat Tokenni configdan olamiz
try:
    from .config import BOT_TOKEN
except ImportError:  # Agar alohida ishga tushirilsa (test uchun)
    # .env faylidan o'qishga harakat qilish
    from dotenv import load_dotenv
    import warnings

    warnings.warn("Could not import from .config, trying dotenv directly for BOT_TOKEN")
    # Loyiha root papkasini topish (taxminan)
    dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    load_dotenv(dotenv_path=dotenv_path)
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("Minimal test uchun ham TELEGRAM_BOT_TOKEN kerak!")

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Minimal holat
STATE_ONE = 1


# Global logger (update kelayotganini tekshirish uchun)
async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"Received update: {update.update_id}")  # Faqat ID ni chiqaramiz qisqalik uchun


# Minimal /start
async def start_minimal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("MINIMAL: /start called")
    keyboard = [[InlineKeyboardButton("TEST TUGMASI", callback_data="test_state_1_callback")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Minimal test. Tugmani bosing:", reply_markup=reply_markup)
    logger.info(f"MINIMAL: Transitioning to state: {STATE_ONE}")
    return STATE_ONE


# Minimal Callback Handler
async def state_1_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    # Callbackga javob berish juda muhim!
    await query.answer("OK!")
    logger.critical("!!!!!!!!!! MINIMAL state_1_callback ISHLADI! Data: %s !!!!!!!!!!", query.data)
    await query.edit_message_text("Minimal test MUVAFFAQIYATLI! Suhbat tugadi.")
    return ConversationHandler.END


# Minimal Cancel
async def cancel_minimal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("MINIMAL: Cancel called.")
    await update.message.reply_text("Minimal suhbat bekor qilindi.")
    return ConversationHandler.END


def main() -> None:
    """Minimal botni ishga tushuradi va handlerlarni qo'shadi."""

    # --- Persistence QAYTA QO'SHILDI ---
    # Yangi fayl nomi ishlatamiz, eski bilan chalkashmasligi uchun
    persistence = PicklePersistence(filepath="bot_storage_minimal_test.pickle")
    # ------------------------------------

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(persistence)  # <-- Qayta qo'shildi
        .build()
    )

    # Global Logger
    application.add_handler(TypeHandler(Update, log_all_updates), group=-1)

    # Minimal Conversation Handler (YANGILANGAN)
    minimal_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_minimal)],
        states={
            STATE_ONE: [
                # --- per_message bu yerdan OLIB TASHLANADI ---
                CallbackQueryHandler(state_1_callback, pattern='^test_state_1_callback$')
                # -------------------------------------------
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_minimal)],
        name="minimal_test_conv",
        persistent=True,  # Bu qoladi (agar persistence'ni test qilayotgan bo'lsak)
        # --- per_message BUTUN ConversationHandler UCHUN BU YERGA QO'SHILADI ---
        per_message=False
        # ----------------------------------------------------------------------
    )
    application.add_handler(minimal_conv_handler)

    logger.info("Starting MINIMAL bot with PERSISTENCE...")  # Log xabari yangilandi
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
