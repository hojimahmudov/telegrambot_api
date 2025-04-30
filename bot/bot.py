import logging

from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, PicklePersistence, filters, ContextTypes
)
from telegram import Update  # <-- Update telegram'dan import qilinadi
from telegram.ext import TypeHandler

# Loyihamizning modullaridan import qilamiz
from .config import (
    BOT_TOKEN, SELECTING_LANG, AUTH_CHECK, WAITING_PHONE, WAITING_OTP, MAIN_MENU,
    ASKING_DELIVERY_TYPE, ASKING_BRANCH, ASKING_LOCATION, ASKING_PAYMENT, ASKING_NOTES
)
from .handlers.common import cancel, debug_callback_in_state_5
from .handlers.start_auth import (
    start, set_language_callback, start_registration_callback,
    contact_handler, otp_handler
)
from .handlers.order import handle_delivery_type_selection, handle_branch_selection, handle_location
from .handlers.main_menu import main_menu_dispatch
from .handlers.callbacks import (
    category_selected_callback, product_selected_callback,
    add_to_cart_callback, quantity_noop_callback, back_button_callback,
    start_checkout_callback, cart_quantity_change_callback, cart_item_delete_callback,
    cart_info_noop_callback, cart_refresh_callback, order_detail_callback, history_page_callback
)
from .utils.api_client import close_api_client  # Klientni yopish uchun

# Logging sozlamalari
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def log_all_updates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Botga kelgan HAR QANDAY update'ni logga yozadi."""
    logger.debug(f"Received update: {update}")


def main() -> None:
    """Botni ishga tushuradi va handlerlarni qo'shadi."""
    # Persistence
    # Fayl yo'li loyiha root papkasiga nisbatan berilishi kerak
    # persistence = PicklePersistence(filepath="bot_storage.pickle")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        # .persistence(persistence)
        .build()
    )

    # Asosiy ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_LANG: [CallbackQueryHandler(set_language_callback, pattern='^set_lang_')],
            # AUTH_CHECK: [CallbackQueryHandler(start_registration_callback, pattern='^start_registration$')],
            # WAITING_PHONE: [MessageHandler(filters.CONTACT & ~filters.COMMAND, contact_handler)],
            # WAITING_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'^\d{4,6}$'), otp_handler)],
            # MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_dispatch)],

            # --- CHECKOUT HOLATLARI ---
            ASKING_DELIVERY_TYPE: [
                CallbackQueryHandler(handle_delivery_type_selection, pattern='^checkout_set_'),
                # Bu holatda ham cancel ishlashi uchun fallback ga qo'shamiz yoki shu yerga
                CallbackQueryHandler(cancel, pattern='^checkout_cancel$'),
                CallbackQueryHandler(debug_callback_in_state_5, pattern='.*')
            ],
            # ASKING_BRANCH: [  # Filial tanlashni kutish holati
            #     CallbackQueryHandler(handle_branch_selection, pattern='^checkout_branch_'),
            #     CallbackQueryHandler(cancel, pattern='^checkout_cancel$')  # Bu yerda ham cancel
            # ],
            # ASKING_LOCATION: [  # Lokatsiya yuborishni kutish holati
            #     MessageHandler(filters.LOCATION & ~filters.COMMAND, handle_location),
            #     # Agar lokatsiya o'rniga boshqa narsa yuborsa?
            #     MessageHandler(filters.ALL & ~filters.COMMAND,
            #                    lambda u, c: u.message.reply_text("Iltimos, lokatsiya yuboring yoki /cancel bosing.")),
            # ],
            # ASKING_PAYMENT: [], # Keyingi qadamlar uchun
            # ASKING_NOTES: [],  # Keyingi qadamlar uchun
            # ----------------------------
        },
        fallbacks=[
            CommandHandler("cancel", cancel),  # Umumiy cancel
            # Checkout cancel ni alohida ushlash ham mumkin, yuqorida qo'shdik
            # CallbackQueryHandler(cancel, pattern='^checkout_cancel$'),
            CommandHandler("start", start)  # Boshiga qaytish
        ],
        name="main_conversation",
        # persistent=True,
    )
    application.add_handler(conv_handler)

    # ConversationHandler'dan tashqari ishlaydigan Callback Handlerlar
    application.add_handler(TypeHandler(Update, log_all_updates), group=-1)
    application.add_handler(CallbackQueryHandler(category_selected_callback, pattern='^cat_'))
    application.add_handler(CallbackQueryHandler(product_selected_callback, pattern='^prod_'))
    application.add_handler(CallbackQueryHandler(add_to_cart_callback, pattern='^add_'))
    application.add_handler(CallbackQueryHandler(quantity_noop_callback, pattern='^p_noop_'))
    application.add_handler(CallbackQueryHandler(quantity_noop_callback, pattern='^p_info_'))
    application.add_handler(CallbackQueryHandler(back_button_callback, pattern='^back_to_'))
    application.add_handler(CallbackQueryHandler(start_checkout_callback, pattern='^start_checkout$'))
    application.add_handler(CallbackQueryHandler(cart_quantity_change_callback, pattern='^cart_(incr|decr)_'))
    application.add_handler(CallbackQueryHandler(cart_item_delete_callback, pattern='^cart_del_'))
    application.add_handler(CallbackQueryHandler(cart_info_noop_callback, pattern='^cart_info_'))
    application.add_handler(CallbackQueryHandler(cart_refresh_callback, pattern='^cart_refresh$'))
    application.add_handler(CallbackQueryHandler(order_detail_callback, pattern='^order_'))
    application.add_handler(CallbackQueryHandler(history_page_callback, pattern='^hist_page_'))

    # Botni ishga tushirish
    logger.info("Starting bot...")
    application.run_polling()

    # Bot to'xtaganda httpx klientni yopish (asinxron)
    # Bu qismni to'g'ri implementatsiya qilish kerak bo'lishi mumkin
    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(close_api_client())


if __name__ == "__main__":
    main()
