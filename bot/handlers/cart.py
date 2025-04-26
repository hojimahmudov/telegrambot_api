# bot/handlers/cart.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest  # <-- BadRequest import qilindi

from ..utils.helpers import get_user_lang
from ..utils.api_client import make_api_request

logger = logging.getLogger(__name__)


async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE, cart_data: dict):
    """API dan kelgan savat ma'lumotlarini formatlab foydalanuvchiga ko'rsatadi."""
    user_id = update.effective_user.id
    lang_code = get_user_lang(context)
    chat_id = update.effective_chat.id

    items = cart_data.get('items', [])
    total_price = cart_data.get('total_price', "0.00")

    message_to_edit = update.callback_query.message if update.callback_query else None  # Yangilash uchun

    if not items:
        cart_empty_text = "Savat bo'sh." if lang_code == 'uz' else "Корзина пуста."
        try:
            if message_to_edit:
                # Bo'sh savatni tahrirlaymiz (agar avvalgi xabar bo'lsa)
                await update.callback_query.edit_message_text(cart_empty_text, reply_markup=None)
                # Agar refresh tugmasi bosilgan bo'lsa, javob beramiz
                await update.callback_query.answer("Savat bo'sh" if lang_code == 'uz' else "Корзина пуста")
            elif update.message:  # Agar "Savat" tugmasi bosilgan bo'lsa
                await update.message.reply_text(cart_empty_text)
        except BadRequest as e:
            if "Message is not modified" in str(e):
                logger.info("Cart is already empty, no edit needed.")
                if update.callback_query: await update.callback_query.answer(
                    "Savat bo'sh" if lang_code == 'uz' else "Корзина пуста")
            else:  # Boshqa BadRequest xatosi
                logger.warning(f"Could not edit/send empty cart message: {e}")
                if not message_to_edit and update.message: await context.bot.send_message(chat_id=chat_id,
                                                                                          text=cart_empty_text)
        except Exception as e:  # Boshqa xatoliklar
            logger.warning(f"Could not edit/send empty cart message: {e}")
            if not message_to_edit and update.message: await context.bot.send_message(chat_id=chat_id,
                                                                                      text=cart_empty_text)
        return

    # Savat bo'sh bo'lmasa, xabar matni va klaviaturani tayyorlaymiz
    message_text = "🛒 <b>Sizning Savatingiz:</b>\n\n" if lang_code == 'uz' else "🛒 <b>Ваша Корзина:</b>\n\n"
    keyboard = []
    for item in items:
        product = item.get('product', {})
        product_name = product.get('name', 'Noma\'lum mahsulot')
        quantity = item.get('quantity', 0)
        item_total = item.get('item_total', 'N/A')
        item_id = item.get('id')
        message_text += f"🔹 <b>{product_name}</b>\n"
        message_text += f"   {quantity} x {product.get('price', 'N/A')} so'm = {item_total} so'm\n"
        keyboard.append([
            InlineKeyboardButton("➖", callback_data=f"cart_decr_{item_id}"),
            InlineKeyboardButton(f" {quantity} ", callback_data=f"cart_info_{item_id}"),
            InlineKeyboardButton("➕", callback_data=f"cart_incr_{item_id}"),
            InlineKeyboardButton("🗑️", callback_data=f"cart_del_{item_id}")
        ])
        message_text += "--------------------\n"
    total_text = f"\n Jami: <b>{total_price}</b> so'm" if lang_code == 'uz' else f"\n Итого: <b>{total_price}</b> сум"
    message_text += total_text
    checkout_button_text = "➡️ Rasmiylashtirish" if lang_code == 'uz' else "➡️ Оформить заказ"
    refresh_button_text = "🔄 Yangilash" if lang_code == 'uz' else "🔄 Обновить"
    keyboard.append([InlineKeyboardButton(checkout_button_text, callback_data="start_checkout")])
    keyboard.append([InlineKeyboardButton(refresh_button_text, callback_data="cart_refresh")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Xabarni yuboramiz yoki tahrirlaymiz
    try:
        if message_to_edit:  # Agar callbackdan kelgan bo'lsa (refresh yoki +/-/del dan keyin)
            logger.debug(f"Attempting to edit cart message {message_to_edit.message_id}")
            await update.callback_query.edit_message_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
            # Agar refresh tugmasi bosilgan bo'lsa, alohida javob beramiz
            if update.callback_query.data == 'cart_refresh':
                await update.callback_query.answer("Savat yangilandi" if lang_code == 'uz' else "Корзина обновлена")
            # Boshqa callbacklar (masalan +/-/del) o'z answer'ini berishi kerak
        elif update.message:  # Agar "Savat" menyu tugmasi bosilgan bo'lsa
            await update.message.reply_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML
            )
    except BadRequest as e:
        # --- XATOLIKNI USHLASH ---
        if "Message is not modified" in str(e):
            logger.info("Cart content hasn't changed. Edit skipped by Telegram.")
            # Foydalanuvchiga o'zgarish yo'qligini bildiramiz (faqat refresh tugmasi uchun)
            if update.callback_query and update.callback_query.data == 'cart_refresh':
                try:
                    await update.callback_query.answer(
                        "Savatda o'zgarish yo'q." if lang_code == 'uz' else "Нет изменений в корзине.")
                except Exception as answer_e:
                    logger.warning(f"Could not answer callback query after no-op edit: {answer_e}")
        else:
            # Boshqa BadRequest xatolarini logga yozamiz
            logger.error(f"Telegram BadRequest during cart send/edit: {e}")
            # Foydalanuvchiga umumiy xatolik haqida xabar berish
            error_text = "Savatni ko'rsatishda Telegram xatoligi." if lang_code == 'uz' else "Ошибка отображения корзины Telegram."
            if update.callback_query:
                await context.bot.send_message(chat_id=chat_id, text=error_text)
            elif update.message:
                await update.message.reply_text(error_text)
    except Exception as e:
        # Boshqa kutilmagan xatoliklar
        logger.error(f"General error sending/editing cart message: {e}", exc_info=True)
        error_text = "Savatni ko'rsatishda noma'lum xatolik." if lang_code == 'uz' else "Неизвестная ошибка при отображении корзины."
        if update.callback_query:
            await context.bot.send_message(chat_id=chat_id, text=error_text)
        elif update.message:
            await update.message.reply_text(error_text)
