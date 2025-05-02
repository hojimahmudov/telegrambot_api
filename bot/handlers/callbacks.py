# bot/handlers/callbacks.py
import logging
from urllib.parse import urlparse, parse_qs

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from .cart import show_cart
from .order import show_order_history

# Loyihadagi boshqa modullardan importlar
from ..utils.helpers import get_user_lang
from ..utils.api_client import make_api_request
# Menyuni ko'rsatish funksiyalarini import qilamiz
from .menu_browse import show_category_list, show_product_list
from ..config import ASKING_DELIVERY_TYPE

logger = logging.getLogger(__name__)


async def cart_quantity_change_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Savatdagi mahsulot sonini o'zgartirish uchun +/- tugmalarini boshqaradi."""
    query = update.callback_query
    # Avval tugma bosilganiga javob beramiz (loading indikatorni olib tashlash uchun)
    # Xabar keyinroq, API javobidan keyin chiqadi
    await query.answer()

    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    try:
        parts = query.data.split('_')  # Masalan: ['cart', 'incr', 'item_id']
        action = parts[1]  # 'incr' yoki 'decr'
        item_id = int(parts[2])
    except (IndexError, ValueError, TypeError):
        logger.warning(f"Invalid cart quantity callback data: {query.data}")
        await query.answer("Xatolik!", show_alert=True)  # Qisqa xatolik alerti
        return

    logger.info(f"User {user_id} requested {action} for cart item {item_id}")

    change = 1 if action == 'incr' else -1

    # 1. Joriy miqdorni bilish uchun avval savatni API dan olamiz
    # (Balki keyinchalik optimallashtirish mumkin, lekin hozircha shunday)
    cart_response = await make_api_request(context, 'GET', 'cart/', user_id)
    if not cart_response or cart_response.get('error'):
        error_text = "Savat ma'lumotlarini olib bo'lmadi." if lang_code == 'uz' else "Не удалось получить данные корзины."
        # Bu yerda xabarni tahrirlash o'rniga yangi xabar yuborish yaxshiroq
        await context.bot.send_message(chat_id=user_id, text=error_text)
        return

    current_quantity = 0
    items = cart_response.get('items', [])
    for item in items:
        if item.get('id') == item_id:
            current_quantity = item.get('quantity', 0)
            break

    if current_quantity == 0:
        logger.warning(f"Cart item {item_id} not found for user {user_id} during quantity change.")
        # Foydalanuvchi eski xabardagi tugmani bosgan bo'lishi mumkin, savatni yangilaymiz
        await show_cart(update, context, cart_response)
        return

    # 2. Yangi miqdorni hisoblaymiz
    new_quantity = current_quantity
    if action == 'incr':
        new_quantity += 1
    elif action == 'decr':
        new_quantity -= 1

    # 3. Minimal miqdorni tekshiramiz (0 dan kichik bo'lsa nima qilish kerak?)
    if new_quantity < 1:
        # Variant 1: Shunchaki minimal 1 da qoldirish
        # new_quantity = 1
        # Variant 2: Agar 1 dan kamaysa, o'chirish (DELETE) logikasini chaqirish
        logger.info(f"Quantity for item {item_id} reached zero via decrement. Deleting item.")
        # await cart_item_delete_callback(update, context) # Bu to'g'ridan-to'g'ri ishlamasligi mumkin
        # Yaxshisi, DELETE API ni chaqiramiz
        delete_data = {"item_id": item_id}
        delete_response = await make_api_request(context, 'DELETE', 'cart/', user_id, data=delete_data)
        # Natijadan qat'iy nazar savatni yangilaymiz
        refreshed_cart_response = await make_api_request(context, 'GET', 'cart/', user_id)
        if refreshed_cart_response and not refreshed_cart_response.get('error'):
            await show_cart(update, context, refreshed_cart_response)
        # Agar miqdor 0 ga tushganda o'chirilsa, shu yerda funksiyadan chiqamiz
        return

    # 4. PATCH API ni chaqiramiz (agar o'chirilmagan bo'lsa)
    update_data = {"item_id": item_id, "change": change}
    update_response = await make_api_request(context, 'PATCH', 'cart/', user_id, data=update_data)

    # 5. Savat ko'rinishini yangilaymiz
    if update_response and not update_response.get('error'):
        logger.info(f"Successfully updated quantity for item {item_id} to {new_quantity}")
        # API dan eng so'nggi savat holatini olamiz
        refreshed_cart_response = await make_api_request(context, 'GET', 'cart/', user_id)
        if refreshed_cart_response and not refreshed_cart_response.get('error'):
            await show_cart(update, context, refreshed_cart_response)  # show_cart xabarni tahrirlaydi
        else:
            error_text = "Savatni yangilashda xatolik."  # ...
            try:
                await query.edit_message_text(error_text)
            except:
                await context.bot.send_message(chat_id=user_id, text=error_text)
    else:
        error_detail = update_response.get('detail', 'N/A') if update_response else 'N/A'
        error_text = f"Miqdorni yangilashda xatolik: {error_detail[:100]}"
        await query.answer(error_text, show_alert=True)  # Xatolikni alert qilamiz


async def cart_item_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Savatdagi mahsulotni o'chirish (🗑️) tugmasini boshqaradi."""
    query = update.callback_query
    await query.answer("O'chirilmoqda...")

    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    try:
        parts = query.data.split('_')  # Masalan: ['cart', 'del', 'item_id']
        item_id = int(parts[2])
    except (IndexError, ValueError, TypeError):
        logger.warning(f"Invalid cart delete callback data: {query.data}")
        await query.answer("Xatolik!", show_alert=True)
        return

    logger.info(f"User {user_id} requested delete for cart item {item_id}")

    # DELETE API ni chaqiramiz
    delete_data = {"item_id": item_id}
    delete_response = await make_api_request(context, 'DELETE', 'cart/', user_id, data=delete_data)

    # API javobidan qat'iy nazar (muvaffaqiyatli yoki 404 - topilmadi), savatni yangilaymiz
    # Chunki agar 404 bo'lsa ham, demak item allaqachon yo'q, foydalanuvchi yangi holatni ko'rishi kerak
    if delete_response and (not delete_response.get('error') or delete_response.get('status_code') == 404):
        logger.info(
            f"Delete request for item {item_id} processed (Status: {delete_response.get('status_code')}). Refreshing cart.")
        refreshed_cart_response = await make_api_request(context, 'GET', 'cart/', user_id)
        if refreshed_cart_response and not refreshed_cart_response.get('error'):
            await show_cart(update, context, refreshed_cart_response)  # show_cart xabarni tahrirlaydi
        else:
            error_text = "Savatni yangilashda xatolik."  # ...
            try:
                await query.edit_message_text(error_text)
            except:
                await context.bot.send_message(chat_id=user_id, text=error_text)
    else:  # Agar DELETE so'rovida boshqa xatolik bo'lsa
        error_detail = delete_response.get('detail', 'N/A') if delete_response else 'N/A'
        error_text = f"O'chirishda xatolik: {error_detail[:100]}"
        await query.answer(error_text, show_alert=True)


async def cart_info_noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles press on the quantity display button in cart (does nothing)."""
    query = update.callback_query
    await query.answer()  # Just acknowledge


async def cart_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the 'Refresh' button in the cart view."""
    query = update.callback_query
    await query.answer("Savat yangilanmoqda...")
    user_id = query.from_user.id
    # Re-fetch and re-display the cart
    cart_response = await make_api_request(context, 'GET', 'cart/', user_id)
    if cart_response and not cart_response.get('error'):
        # Need to import show_cart here as well
        from .cart import show_cart
        # Edit the existing message with the new cart data
        await show_cart(update, context, cart_response)  # show_cart needs to handle edits
    else:
        error_detail = cart_response.get('detail', 'N/A') if cart_response else 'N/A'
        await query.answer(f"Yangilashda xatolik: {error_detail}", show_alert=True)


# Kategoriya tanlandi
async def category_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    try:
        if not query.data or not query.data.startswith('cat_'): raise ValueError("Invalid callback data")
        category_id = int(query.data.split('_')[1])
        logger.info(f"User {user_id} selected category ID: {category_id}")
        await show_product_list(update, context, category_id)  # Mahsulot ro'yxatini ko'rsatamiz
    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f"Invalid category callback data: {query.data} - Error: {e}")
        try:
            await query.edit_message_text("Xatolik: Noto'g'ri kategoriya.")
        except Exception as edit_e:
            logger.error(f"Failed edit on invalid cat data: {edit_e}")


# Mahsulot tanlandi
async def product_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    try:
        if not query.data or not query.data.startswith('prod_'): raise ValueError("Invalid callback data")
        product_id = int(query.data.split('_')[1])
    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f"Invalid product callback data: {query.data} - Error: {e}")
        try:
            await query.edit_message_text("Xatolik: Noto'g'ri mahsulot.")
        except Exception as edit_e:
            logger.error(f"Failed edit on invalid prod data: {edit_e}")
        return

    logger.info(f"User {user_id} selected product ID: {product_id}")
    loading_text = "Mahsulot yuklanmoqda..." if lang_code == 'uz' else "Загрузка продукта..."
    try:
        await query.edit_message_text(text=loading_text)
    except Exception:
        await context.bot.send_message(chat_id=user_id, text=loading_text)

    product_response = await make_api_request(context, 'GET', f'products/{product_id}/',
                                              user_id)  # Token shart emas bunga ham

    if product_response and not product_response.get('error'):
        product = product_response
        category_id = context.user_data.get('current_category_id', None)
        caption = f"<b>{product.get('name', 'Nomsiz')}</b>\n\n"
        description = product.get('description')
        if description: caption += f"<pre>{description}</pre>\n\n"
        caption += f"Narxi: {product.get('price', 'N/A')} so'm"
        qty = 1
        minus_button = InlineKeyboardButton("-", callback_data=f"p_noop_{product_id}")
        qty_button = InlineKeyboardButton(str(qty), callback_data=f"p_info_{product_id}")
        plus_button = InlineKeyboardButton("+", callback_data=f"p_noop_{product_id}")
        add_cart_button_text = "🛒 Savatga" if lang_code == 'uz' else "🛒 В корзину"
        add_cart_button = InlineKeyboardButton(add_cart_button_text, callback_data=f"add_{product_id}")
        back_button_text = "< Ortga" if lang_code == 'uz' else "< Назад"
        back_button_callback_data = f"back_to_prod_list_{category_id}" if category_id else "back_to_categories"
        back_button = InlineKeyboardButton(back_button_text, callback_data=back_button_callback_data)
        keyboard = [[minus_button, qty_button, plus_button], [add_cart_button], [back_button]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        photo_url = product.get('image_url')

        try:
            await query.delete_message()
        except Exception:
            pass

        if photo_url:
            try:
                await context.bot.send_photo(chat_id=user_id, photo=photo_url, caption=caption,
                                             reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Failed to send product photo {photo_url}: {e}")
                await context.bot.send_message(chat_id=user_id, text=caption, reply_markup=reply_markup,
                                               parse_mode=ParseMode.HTML)
        else:
            await context.bot.send_message(chat_id=user_id, text=caption, reply_markup=reply_markup,
                                           parse_mode=ParseMode.HTML)
    else:
        error_detail = product_response.get('detail', 'N/A') if product_response else 'N/A'
        reply_text = f"Mahsulotni olib bo'lmadi: {error_detail}" if lang_code == 'uz' else f"Не удалось получить продукт: {error_detail}"
        try:
            await query.edit_message_text(text=reply_text)
        except Exception:
            await context.bot.send_message(chat_id=user_id, text=reply_text)


# Savatga qo'shish callback'i
async def add_to_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Savatga qo'shilmoqda...")
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    try:
        if not query.data or not query.data.startswith('add_'): raise ValueError("Invalid callback data")
        product_id = int(query.data.split('_')[1])
    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f"Invalid add_to_cart callback: {query.data} - {e}")
        await query.answer("Xatolik!", show_alert=True)
        return
    logger.info(f"User {user_id} adding product {product_id} to cart")
    cart_data = {"product_id": product_id, "quantity": 1}
    # Savatga qo'shish uchun token kerak! make_api_request buni o'zi qo'shadi
    api_response = await make_api_request(context, 'POST', 'cart/', user_id, data=cart_data)
    if api_response and not api_response.get('error'):
        success_text = "✅ Savatga qo'shildi!" if lang_code == 'uz' else "✅ Добавлено в корзину!"
        await query.answer(success_text, show_alert=False)
    else:
        # Agar 401 kelsa, make_api_request log yozadi va None qaytaradi
        if api_response and api_response.get('status_code') == 401:
            # Foydalanuvchiga xabar berish kerak bo'lishi mumkin
            await context.bot.send_message(chat_id=user_id,
                                           text="Savatga qo'shish uchun tizimga qayta kiring (/start).")
        else:
            error_detail = api_response.get('detail', 'N/A') if api_response else 'N/A'
            logger.warning(f"Failed add to cart for user {user_id}, product {product_id}: {error_detail}")
            error_text = f"Xatolik: {error_detail[:100]}"
            await query.answer(error_text, show_alert=True)


# +/-/son tugmalari uchun placeholder
async def quantity_noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer("Bu tugma hozircha aktiv emas.")
    logger.info(f"User {query.from_user.id} pressed quantity noop button: {query.data}")


# Ortga tugmasi callback'i
async def back_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    callback_data = query.data
    logger.info(f"User {user_id} pressed back button: {callback_data}")
    try:
        await query.delete_message()
    except Exception as e:
        logger.warning(f"Could not delete message on back press: {e}")

    if callback_data == 'back_to_categories':
        await show_category_list(update, context)
    elif callback_data.startswith('back_to_prod_list_'):
        try:
            category_id = int(callback_data.split('_')[-1])
            await show_product_list(update, context, category_id)
        except (IndexError, ValueError, TypeError):
            logger.warning(f"Invalid back_to_prod_list callback: {callback_data}")
            await show_category_list(update, context)  # Kategoriyalarga qaytaramiz


# Checkout boshlash callback'i (placeholder)
async def start_checkout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:  # Endi state qaytaradi
    """ "Rasmiylashtirish" tugmasi bosilganda ishlaydi va checkout suhbatini boshlaydi."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    logger.info(f"User {user_id} initiated checkout.")

    # Yetkazib berish turini tanlash tugmalarini yaratamiz
    del_type_text = "Yetkazib berish" if lang_code == 'uz' else "Доставка"
    pickup_type_text = "Olib ketish" if lang_code == 'uz' else "Самовывоз"
    cancel_text = "Bekor qilish" if lang_code == 'uz' else "Отмена"

    keyboard = [
        [
            InlineKeyboardButton(del_type_text, callback_data="checkout_set_delivery"),
            InlineKeyboardButton(pickup_type_text, callback_data="checkout_set_pickup")
        ],
        [InlineKeyboardButton(f"❌ {cancel_text}", callback_data="checkout_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = "Yetkazib berish turini tanlang:" if lang_code == 'uz' else "Выберите тип доставки:"

    # Oldingi savat xabarini tahrirlaymiz
    try:
        await query.edit_message_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML  # Agar formatlash bo'lsa
        )
    except Exception as e:
        logger.error(f"Error editing message to start checkout: {e}")
        # Agar tahrirlab bo'lmasa, yangi xabar yuboramiz
        await context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup)
    logger.info(f"Transitioning to state: {ASKING_DELIVERY_TYPE}")
    # Keyingi holatni qaytaramiz
    return ASKING_DELIVERY_TYPE  # Yetkazib berish turini kutish holati


async def order_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ "Batafsil" (order_{id}) tugmasi bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    try:
        order_id = int(query.data.split('_')[1])
        logger.info(f"User {user_id} requested details for order {order_id}")
        # TODO: Call GET /orders/{order_id}/ API
        # TODO: Create show_order_detail(update, context, order_data) function in order.py
        # TODO: Call show_order_detail to display info
        await query.edit_message_text(f"Buyurtma #{order_id} detallari hali ko'rsatilmaydi.")
    except (IndexError, ValueError, TypeError):
        logger.warning(f"Invalid order detail callback: {query.data}")
        await query.edit_message_text("Xatolik.")


async def history_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Buyurtmalar tarixi sahifalash tugmalari bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    callback_data = query.data  # 'hist_page_{page_num}' yoki 'hist_page_url_{url}'

    logger.info(f"User {user_id} requested history page: {callback_data}")

    endpoint = 'orders/history/'  # Standart endpoint
    params = {}
    if callback_data.startswith('hist_page_url_'):
        # Agar to'liq URL bo'lsa, undan faqat path va query qismini olish kerak
        # Bu xavfliroq, yaxshisi page raqamini ishlatish
        full_url = callback_data[len('hist_page_url_'):]
        parsed_url = urlparse(full_url)
        endpoint = parsed_url.path.replace('/api/v1/', '', 1)  # API base URL ni olib tashlash
        params = parse_qs(parsed_url.query)  # Query parametrlarni dict ga o'giradi
        # parse_qs list qaytaradi: {'page': ['2']} -> {'page': '2'} qilish kerak
        params = {k: v[0] for k, v in params.items() if len(v) == 1}

    elif callback_data.startswith('hist_page_'):
        try:
            page_num = int(callback_data.split('_')[-1])
            params = {'page': page_num}
        except (ValueError, IndexError):
            logger.warning(f"Invalid history page callback data: {callback_data}")
            await query.edit_message_text("Xatolik: Sahifa topilmadi.")
            return

    # API ga yangi sahifa uchun so'rov yuboramiz
    history_response = await make_api_request(context, 'GET', endpoint, user_id, params=params)

    if history_response and not history_response.get('error'):
        await show_order_history(update, context, history_response)  # Xabarni yangilaymiz
    elif history_response and history_response.get('status_code') == 404:
        await query.answer("Bu sahifa mavjud emas.", show_alert=True)
    else:
        error_detail = history_response.get('detail', 'N/A') if history_response else 'N/A'
        await query.answer(f"Sahifani yuklashda xatolik: {error_detail[:100]}", show_alert=True)
