# bot/bot.py (MINIMAL TEST KODI)
import logging
import os
import sys  # <-- sys import qilindi
import django  # <-- django import qilindi
from .utils.db_utils import init_db

print(f"DEBUG: Running script from: {__file__}")

# --- Django Sozlamalarini Yuklash ---
try:
    # Skript ishlayotgan papkadan loyiha root papkasiga chiqish
    # Hozirgi fayl: D:\Hojiakbar\telegrambot_api\bot\bot.py
    # Loyiha root: D:\Hojiakbar\telegrambot_api
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"DEBUG: Adding project root to path: {project_root}")
    if project_root not in sys.path:
        sys.path.append(project_root)

    # Django settings modulini ko'rsatamiz ('backend_config' o'rniga loyiha sozlamalari papkangiz nomi)
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_config.settings')

    print("DEBUG: Calling django.setup()...")
    django.setup()
    print("DEBUG: django.setup() completed.")
except Exception as e:
    print(f"CRITICAL ERROR: Failed to setup Django: {e}")
    # Django sozlamalari yuklanmasa, bot ishlay olmaydi
    sys.exit("Django sozlamalarini yuklab bo'lmadi. Chiqilmoqda.")
# --- Django Sozlamalari Yuklandi ---

from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, PicklePersistence, filters, ContextTypes
)
from telegram import Update  # <-- Update telegram'dan import qilinadi
# Loyihamizning modullaridan import qilamiz
from .config import (
    BOT_TOKEN, SELECTING_LANG, AUTH_CHECK, WAITING_PHONE, MAIN_MENU,
    ASKING_DELIVERY_TYPE, ASKING_BRANCH, ASKING_LOCATION, ASKING_PAYMENT, ASKING_NOTES, CHOOSING_PHONE_METHOD,
    WAITING_MANUAL_PHONE, CONFIRMING_LOCATION, SELECTING_ADDRESS_OR_NEW, ASKING_SAVE_NEW_ADDRESS, ENTERING_ADDRESS_NAME,
)
from .handlers.common import cancel
from .handlers.start_auth import (
    start, set_language_callback, start_registration_callback,
    contact_handler, choose_phone_method_share_callback, choose_phone_method_manual_callback,
    manual_phone_handler
)
from .handlers.order import handle_delivery_type_selection, handle_branch_selection, handle_location, \
    handle_payment_selection, handle_notes, skip_notes_callback, confirm_location_callback, \
    handle_saved_address_selection, handle_send_new_location_callback, handle_save_new_address_decision_callback, \
    handle_address_name_input, skip_address_name_callback
from .handlers.main_menu import main_menu_dispatch
from .handlers.callbacks import (
    category_selected_callback, product_selected_callback,
    back_button_callback,
    start_checkout_callback, cart_quantity_change_callback, cart_item_delete_callback,
    cart_info_noop_callback, cart_refresh_callback, order_detail_callback, history_page_callback,
    cancel_order_callback, back_to_history_callback, branch_location_callback, product_detail_qty_change_callback,
    product_detail_qty_info_callback, product_detail_add_to_cart_callback
)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Botni ishga tushuradi va handlerlarni qo'shadi."""
    # Persistence
    init_db()
    persistence = PicklePersistence(filepath="bot_storage.pickle")  # Asl fayl nomi

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(persistence)  # Persistence yoqilgan
        .build()
    )

    # --- Handlerlarni Qo'shish Tartibi ---

    # 1. Global logger (agar kerak bo'lsa, debug uchun)
    # application.add_handler(TypeHandler(Update, log_all_updates), group=-1) # Hozircha o'chirib turamiz

    # 2. Global CallbackQuery Handlerlar (ConversationHandler'dan oldin, block=False bilan)
    application.add_handler(CallbackQueryHandler(category_selected_callback, pattern='^cat_', block=False))
    application.add_handler(CallbackQueryHandler(product_selected_callback, pattern='^prod_', block=False))
    application.add_handler(
        CallbackQueryHandler(product_detail_qty_change_callback, pattern='^pdetail_(incr|decr)_', block=False))
    application.add_handler(
        CallbackQueryHandler(product_detail_qty_info_callback, pattern='^pdetail_qtyinfo_', block=False))
    application.add_handler(
        CallbackQueryHandler(product_detail_add_to_cart_callback, pattern='^pdetail_add_', block=False))
    application.add_handler(CallbackQueryHandler(back_to_history_callback, pattern='^back_to_history$', block=False))
    application.add_handler(CallbackQueryHandler(back_button_callback, pattern='^back_to_', block=False))
    # application.add_handler(CallbackQueryHandler(start_checkout_callback, pattern='^start_checkout$', block=False))
    application.add_handler(
        CallbackQueryHandler(cart_quantity_change_callback, pattern='^cart_(incr|decr)_', block=False))
    application.add_handler(CallbackQueryHandler(cart_item_delete_callback, pattern='^cart_del_', block=False))
    application.add_handler(CallbackQueryHandler(cart_info_noop_callback, pattern='^cart_info_', block=False))
    application.add_handler(CallbackQueryHandler(cart_refresh_callback, pattern='^cart_refresh$', block=False))
    application.add_handler(CallbackQueryHandler(order_detail_callback, pattern='^order_', block=False))
    application.add_handler(CallbackQueryHandler(history_page_callback, pattern='^hist_page_', block=False))
    application.add_handler(CallbackQueryHandler(cancel_order_callback, pattern='^cancel_order_', block=False))
    application.add_handler(CallbackQueryHandler(branch_location_callback, pattern='^branch_loc_', block=False))

    # 3. Asosiy ConversationHandler (persistent=True va per_message=False bilan)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_LANG: [
                # per_message=False BU YERDAN OLINDI!
                CallbackQueryHandler(set_language_callback, pattern='^set_lang_')
            ],
            AUTH_CHECK: [
                # per_message=False BU YERDAN OLINDI!
                CallbackQueryHandler(start_registration_callback, pattern='^start_registration$')
            ],
            CHOOSING_PHONE_METHOD: [
                CallbackQueryHandler(choose_phone_method_share_callback, pattern='^reg_share_contact$'),
                CallbackQueryHandler(choose_phone_method_manual_callback, pattern='^reg_enter_phone$'),
                CallbackQueryHandler(cancel, pattern='^cancel_registration$')  # Registratsiyani bekor qilish
            ],
            WAITING_PHONE: [MessageHandler(filters.CONTACT & ~filters.COMMAND, contact_handler)],
            WAITING_MANUAL_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_phone_handler)
            ],
            # WAITING_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'^\d{4,6}$'), otp_handler)],
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_dispatch),
                        CallbackQueryHandler(start_checkout_callback, pattern='^start_checkout$')
                        ],
            ASKING_DELIVERY_TYPE: [
                # per_message=False BU YERDAN OLINDI!
                CallbackQueryHandler(handle_delivery_type_selection, pattern='^checkout_set_'),
                # per_message=False BU YERDAN OLINDI!
                CallbackQueryHandler(cancel, pattern='^checkout_cancel$')
            ],
            ASKING_BRANCH: [
                # per_message=False BU YERDAN OLINDI!
                CallbackQueryHandler(handle_branch_selection, pattern='^checkout_branch_'),
                # per_message=False BU YERDAN OLINDI!
                CallbackQueryHandler(cancel, pattern='^checkout_cancel$')
            ],
            ASKING_LOCATION: [
                MessageHandler(filters.LOCATION & ~filters.COMMAND, handle_location),
                MessageHandler(filters.ALL & ~filters.COMMAND, lambda u, c: u.message.reply_text("...")),
                # per_message=False BU YERDAN OLINDI!
                CallbackQueryHandler(cancel, pattern='^checkout_cancel$')
            ],
            CONFIRMING_LOCATION: [
                CallbackQueryHandler(confirm_location_callback, pattern='^loc_confirm_'),
                CallbackQueryHandler(cancel, pattern='^checkout_cancel$')  # Bu yerda ham cancel
            ],
            SELECTING_ADDRESS_OR_NEW: [
                CallbackQueryHandler(handle_saved_address_selection, pattern='^use_saved_addr_'),
                CallbackQueryHandler(handle_send_new_location_callback, pattern='^send_new_location$'),
                CallbackQueryHandler(cancel, pattern='^checkout_cancel$')
            ],
            ASKING_SAVE_NEW_ADDRESS: [
                CallbackQueryHandler(handle_save_new_address_decision_callback, pattern='^save_new_addr_'),
                CallbackQueryHandler(cancel, pattern='^checkout_cancel$')
            ],
            ENTERING_ADDRESS_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_address_name_input),
                CallbackQueryHandler(skip_address_name_callback, pattern='^save_addr_skip_name$'),
                CommandHandler("skip_address_name", skip_address_name_callback),  # /skip_address_name buyrug'i uchun
                CallbackQueryHandler(cancel, pattern='^checkout_cancel$')
            ],
            ASKING_PAYMENT: [
                CallbackQueryHandler(handle_payment_selection, pattern='^checkout_payment_'),
                CallbackQueryHandler(cancel, pattern='^checkout_cancel$')
            ],
            ASKING_NOTES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_notes),  # Matnli izohni ushlash
                CallbackQueryHandler(skip_notes_callback, pattern='^checkout_skip_notes$'),  # Skip tugmasi
                CallbackQueryHandler(cancel, pattern='^checkout_cancel$')  # Bekor qilish
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        name="main_conversation",
        persistent=True,
        # --- per_message BUTUN ConversationHandler UCHUN FAQAT SHU YERGA QO'SHILADI ---
        per_message=False
        # --------------------------------------------------------------------------
    )
    application.add_handler(conv_handler)

    # 4. Boshqa global Command/Message Handlerlar (hozircha yo'q)

    logger.info("Starting bot...")
    application.run_polling(drop_pending_updates=True)  # Eskirgan update'larni o'tkazib yuborish


if __name__ == "__main__":
    main()
