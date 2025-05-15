# bot/handlers/callbacks.py
import logging
from urllib.parse import urlparse, parse_qs

import datetime
from django.utils import timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from .cart import show_cart
from .order import show_order_history, show_order_detail
from ..keyboards import get_product_detail_keyboard

# Loyihadagi boshqa modullardan importlar
from ..utils.helpers import get_user_lang
from ..utils.api_client import make_api_request
# Menyuni ko'rsatish funksiyalarini import qilamiz
from .menu_browse import show_category_list, show_product_list
from ..config import ASKING_DELIVERY_TYPE, SELECTING_LANG

logger = logging.getLogger(__name__)


async def cart_quantity_change_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Savatdagi mahsulot sonini o'zgartirish uchun +/- tugmalarini boshqaradi."""
    query = update.callback_query
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    try:
        parts = query.data.split('_')  # Masalan: ['cart', 'incr', 'item_id']
        action_type = parts[1]  # 'incr' yoki 'decr'
        item_id = int(parts[2])
    except (IndexError, ValueError, TypeError):
        logger.warning(f"Invalid cart quantity callback data: {query.data} for user {user_id}")
        await query.answer("Xatolik: Noto'g'ri so'rov.", show_alert=True)
        return

    # Foydalanuvchiga darhol javob (loading state)
    processing_text = "Bajarilmoqda..." if lang_code == 'uz' else "Обработка..."
    await query.answer(processing_text)

    logger.info(f"User {user_id} requested {action_type} for cart item {item_id}")

    change = 1 if action_type == 'incr' else -1

    update_data = {"item_id": item_id, "change": change}
    api_response = await make_api_request(context, 'PATCH', 'cart/', user_id, data=update_data)

    if api_response and not api_response.get('error'):
        logger.info(f"Successfully processed quantity change for item {item_id}. Refreshing cart.")
        await show_cart(update, context, api_response)  # API javobidagi savatni ko'rsatamiz
        # query.answer() yuqorida chaqirilgan, bu yerda muvaffaqiyat haqida qo'shimcha alert shart emas
    elif api_response and api_response.get('status_code') == 401:
        logger.warning(f"Unauthorized quantity change for user {user_id}, item {item_id}.")
        # make_api_request xabar yuborgan bo'lishi kerak
    else:
        error_detail = api_response.get('detail',
                                        'Noma\'lum xatolik') if api_response else 'Server bilan bog\'lanish xatosi'
        logger.error(f"Failed to update quantity for item {item_id}, user {user_id}: {error_detail}")
        error_text_alert = "Xatolik yuz berdi!" if lang_code == 'uz' else "Произошла ошибка!"
        await query.answer(error_text_alert, show_alert=True)


async def cart_item_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Savatdagi mahsulotni o'chirish (🗑️) tugmasini boshqaradi."""
    query = update.callback_query
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    try:
        parts = query.data.split('_')  # Masalan: ['cart', 'del', 'item_id']
        item_id = int(parts[2])
    except (IndexError, ValueError, TypeError):
        logger.warning(f"Invalid cart delete callback data: {query.data} for user {user_id}")
        await query.answer("Xatolik: Noto'g'ri so'rov.", show_alert=True)
        return

    deleting_text = "O'chirilmoqda..." if lang_code == 'uz' else "Удаление..."
    await query.answer(deleting_text)  # Darhol javob

    logger.info(f"User {user_id} requested delete for cart item {item_id}")

    delete_data = {"item_id": item_id}
    api_response = await make_api_request(context, 'DELETE', 'cart/', user_id, data=delete_data)

    if api_response and not api_response.get('error'):
        logger.info(f"Delete request for item {item_id} processed. Refreshing cart.")
        await show_cart(update, context, api_response)
    elif api_response and api_response.get('status_code') == 401:
        logger.warning(f"Unauthorized delete for user {user_id}, item {item_id}.")
    elif api_response and api_response.get('status_code') == 404:  # Mahsulot allaqachon yo'q
        logger.info(f"Item {item_id} not found for delete, likely already gone. Refreshing cart.")
        current_cart_data = await make_api_request(context, 'GET', 'cart/', user_id)
        if current_cart_data and not current_cart_data.get('error'):
            await show_cart(update, context, current_cart_data)
        else:
            error_text = "Savatni yangilab bo'lmadi."  # ...
            await context.bot.send_message(chat_id=user_id, text=error_text)  # Yangi xabar
    else:
        error_detail = api_response.get('detail',
                                        'Noma\'lum xatolik') if api_response else 'Server bilan bog\'lanish xatosi'
        logger.error(f"Failed to delete item {item_id} for user {user_id}: {error_detail}")
        error_text_alert = "O'chirishda xatolik!" if lang_code == 'uz' else "Ошибка удаления!"
        await query.answer(error_text_alert, show_alert=True)


async def cart_info_noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles press on the quantity display button in cart (does nothing)."""
    query = update.callback_query
    await query.answer()  # Just acknowledge


async def cart_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    refreshing_text = "Savat yangilanmoqda..." if lang_code == 'uz' else "Обновление корзины..."
    await query.answer(refreshing_text)

    logger.info(f"User {user_id} requested cart refresh.")
    cart_response = await make_api_request(context, 'GET', 'cart/', user_id)
    if cart_response and not cart_response.get('error'):
        await show_cart(update, context, cart_response)
    elif cart_response and cart_response.get('status_code') == 401:
        pass  # make_api_request xabar bergan
    else:
        error_detail = cart_response.get('detail', 'N/A') if cart_response else 'N/A'
        error_text_alert = "Yangilashda xatolik!" if lang_code == 'uz' else "Ошибка обновления!"
        await query.answer(error_text_alert, show_alert=True)
        logger.warning(f"Failed to refresh cart for user {user_id}: {error_detail}")


# Kategoriya tanlandi
async def category_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kategoriya tugmasi bosilganda ishlaydi, avvalgi xabarni o'chirib, mahsulot nomlari ro'yxatini chiqaradi."""
    query = update.callback_query
    await query.answer()  # Callbackga javob beramiz
    user_id = query.from_user.id
    # lang_code = get_user_lang(context) # Agar show_product_list ichida ishlatilmasa, bu yerda shart emas

    try:
        # Callback datadan kategoriya ID sini ajratib olamiz ('cat_<ID>')
        if not query.data or not query.data.startswith('cat_'):
            raise ValueError("Invalid callback data for category selection")
        category_id = int(query.data.split('_')[1])
    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f"Invalid category callback data: {query.data} - Error: {e}")
        # Xatolik haqida qisqa javob beramiz, xabarni tahrirlamaymiz
        await query.answer("Xatolik: Noto'g'ri kategoriya tanlandi.", show_alert=True)
        return

    logger.info(f"User {user_id} selected category ID: {category_id} to view products.")

    # --- AVVALGI XABARNI O'CHIRAMIZ ---
    if query.message:  # Agar callback xabar bilan bog'liq bo'lsa
        try:
            await query.delete_message()
            logger.info(f"Deleted category list message for user {user_id}")
        except Exception as e:
            # Agar o'chirishda xatolik bo'lsa (masalan, xabar juda eski), log yozamiz
            logger.warning(f"Could not delete category list message: {e}")
    # ---------------------------------

    # Endi mahsulotlar ro'yxatini ko'rsatish uchun show_product_list ni chaqiramiz
    # show_product_list o'zi yangi "Yuklanmoqda..." xabarini chiqaradi va keyin mahsulotlarni
    await show_product_list(update, context, category_id)


# Mahsulot tanlandi
async def product_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mahsulot nomi tugmasi bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()  # Callbackga tez javob beramiz
    user_id = query.from_user.id
    chat_id = update.effective_chat.id  # Chat ID ni olamiz
    lang_code = get_user_lang(context)

    product_id_to_fetch = -1  # Standart noto'g'ri qiymat
    try:
        if not query.data or not query.data.startswith('prod_'):
            raise ValueError("Invalid callback data for product selection")
        product_id_to_fetch = int(query.data.split('_')[1])
    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f"Invalid product callback data: {query.data} - Error: {e}")
        # Xatolik haqida yangi xabar yuboramiz, chunki avvalgi xabar qanday ekanligi noma'lum
        await context.bot.send_message(chat_id=chat_id, text="Xatolik: Noto'g'ri mahsulot tanlandi.")
        return

    logger.info(f"User {user_id} selected product ID: {product_id_to_fetch} for detail view.")

    # 1. Avvalgi xabarni (mahsulotlar ro'yxati tugmalari bo'lgan) o'chiramiz
    if query.message:
        try:
            await query.delete_message()
            logger.info(f"Deleted product list message for user {user_id}")
        except Exception as e:
            logger.warning(f"Could not delete product list message: {e}")

    # 2. Yangi "Mahsulot yuklanmoqda..." xabarini yuboramiz
    loading_text = "Mahsulot ma'lumotlari yuklanmoqda..." if lang_code == 'uz' else "Загрузка данных о продукте..."
    sent_loading_msg = None
    try:
        sent_loading_msg = await context.bot.send_message(chat_id=chat_id, text=loading_text)
    except Exception as e:
        logger.error(f"Failed to send 'Loading product details...' message: {e}", exc_info=True)
        return  # Agar bu xabarni ham yubora olmasak, davom etmaymiz

    # 3. API dan mahsulot detallarini olamiz
    product_response = await make_api_request(context, 'GET', f'products/{product_id_to_fetch}/', user_id)

    # 4. Yuborilgan "Yuklanmoqda..." xabarini o'chiramiz
    if sent_loading_msg:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=sent_loading_msg.message_id)
        except Exception as e:
            logger.warning(f"Could not delete 'Loading product details...' message: {e}")

    # 5. API javobini qayta ishlab, yakuniy mahsulot detallari xabarini yuboramiz
    if product_response and not product_response.get('error'):
        product = product_response
        category_id_for_back = context.user_data.get('current_category_id')

        # Kontekstga joriy mahsulot va miqdorni saqlaymiz
        context.user_data['product_detail_interaction'] = {
            'product_id': product_id_to_fetch,
            'quantity': 1,  # Boshlang'ich miqdor
            'category_id': category_id_for_back
        }

        caption = f"<b>{product.get('name', 'Nomsiz')}</b>\n\n"
        description = product.get('description')
        if description: caption += f"<pre>{description}</pre>\n\n"
        caption += f"Narxi: {product.get('price', 'N/A')} so'm"

        reply_markup = get_product_detail_keyboard(
            product_id=product_id_to_fetch,
            category_id=category_id_for_back,
            quantity=1,  # Boshlang'ich miqdor
            lang_code=lang_code
        )

        photo_url = product.get('image_url')
        if photo_url:
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=photo_url, caption=caption,
                                             reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            except Exception as e_photo:
                logger.error(f"Failed to send product photo {photo_url}: {e_photo}")
                # Rasm bilan yuborib bo'lmasa, matn bilan yuboramiz
                await context.bot.send_message(chat_id=chat_id, text=caption, reply_markup=reply_markup,
                                               parse_mode=ParseMode.HTML)
        else:  # Rasm yo'q bo'lsa
            await context.bot.send_message(chat_id=chat_id, text=caption, reply_markup=reply_markup,
                                           parse_mode=ParseMode.HTML)
    else:  # API Xatoligi
        error_detail = product_response.get('detail',
                                            'Noma\'lum xatolik') if product_response else 'Server bilan bog\'lanish xatosi'
        error_text = f"Mahsulot ma'lumotini olib bo'lmadi: {error_detail}" if lang_code == 'uz' else f"Не удалось получить данные продукта: {error_detail}"
        await context.bot.send_message(chat_id=chat_id, text=error_text)


async def product_detail_qty_change_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()  # Tez javob
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    interaction_data = context.user_data.get('product_detail_interaction')
    if not interaction_data or not query.message:
        logger.warning(f"No current_product_interaction for user {user_id} on qty change.")
        return

    product_id = interaction_data['product_id']
    current_quantity = interaction_data['quantity']
    category_id_for_back = interaction_data.get('category_id')

    action = query.data.split('_')[1]  # pdetail_ACTION_productid

    if action == 'incr':
        current_quantity += 1
    elif action == 'decr':
        current_quantity = max(1, current_quantity - 1)  # Minimal 1

    context.user_data['product_detail_interaction']['quantity'] = current_quantity
    logger.info(f"User {user_id} changed temp qty for product {product_id} to {current_quantity}")

    reply_markup = get_product_detail_keyboard(
        product_id=product_id,
        category_id=category_id_for_back,
        quantity=current_quantity,
        lang_code=lang_code
    )
    try:
        await query.edit_message_reply_markup(reply_markup=reply_markup)
    except Exception as e:
        logger.error(
            f"Error editing reply markup for qty change: {e} - Message text might be too similar or unchanged.")
        # Agar edit_message_reply_markup ishlamasa (ba'zan shunday bo'ladi, agar xabar o'zgarmasa),
        # shunchaki query.answer() yetarli bo'lishi mumkin.


async def product_detail_qty_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Miqdor ko'rsatilgan tugma bosilganda ishlaydi (hech narsa qilmaydi)."""
    query = update.callback_query
    await query.answer()  # Shunchaki tasdiqlaymiz


async def product_detail_add_to_cart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    interaction_data = context.user_data.get('product_detail_interaction')
    if not interaction_data:
        logger.warning(f"No current_product_interaction for user {user_id} on pdetail_add.")
        # Agar kontekst topilmasa, xatolik haqida qisqa alert beramiz
        await query.answer("Xatolik yuz berdi, iltimos qaytadan urinib ko'ring.", show_alert=True)
        return

    product_id_from_context = interaction_data['product_id']
    category_id_for_back = interaction_data.get('category_id')  # Ortga qaytish uchun kategoriya IDsi

    try:  # Callback datadan product_id ni olamiz, solishtirish uchun
        product_id_from_callback = int(query.data.split('_')[-1])
        if product_id_from_context != product_id_from_callback:
            logger.error(f"Mismatch product ID in context vs callback for user {user_id}")
            await query.answer("Ichki tizim xatoligi!", show_alert=True)
            return
    except (IndexError, ValueError, TypeError):
        logger.error(f"Invalid product_id in callback data for pdetail_add: {query.data}")
        await query.answer("Ichki xatolik (mahsulot IDsi)!", show_alert=True)
        return

    quantity_to_add = interaction_data['quantity']
    logger.info(
        f"User {user_id} adding product {product_id_from_context} (qty: {quantity_to_add}) to cart from detail.")

    # API ga savatga qo'shish so'rovini yuboramiz
    cart_data = {"product_id": product_id_from_context, "quantity": quantity_to_add}
    api_response = await make_api_request(context, 'POST', 'cart/', user_id, data=cart_data)

    if api_response and not api_response.get('error'):
        success_text = f"✅ {quantity_to_add} dona mahsulot savatga qo'shildi!" if lang_code == 'uz' else f"✅ {quantity_to_add} шт. товара добавлено в корзину!"
        await query.answer(success_text, show_alert=True)  # Muvaffaqiyatli qo'shilganini alert qilamiz

        # --- Mahsulotlar ro'yxatiga qaytish logikasi ---
        # Joriy 'product_detail_interaction' ni tozalaymiz, chunki bu ko'rinishdan chiqyapmiz
        if 'product_detail_interaction' in context.user_data:
            del context.user_data['product_detail_interaction']

        if category_id_for_back:
            logger.info(f"Returning to product list for category {category_id_for_back} after adding to cart.")
            # Avvalgi (mahsulot detali) xabarini o'chiramiz
            try:
                if query.message: await query.delete_message()
            except Exception as e:
                logger.warning(f"Could not delete product detail message before showing product list: {e}")

            # Mahsulotlar ro'yxatini ko'rsatamiz (show_product_list yangi xabar yuboradi)
            await show_product_list(update, context, category_id_for_back)
        else:
            # Agar qandaydir sabab bilan kategoriya ID topilmasa, xatolik yoki asosiy menyu
            logger.warning(f"No category_id found to return to product list for user {user_id}. Message not changed.")
            # Bu holatda, shunchaki alert chiqqan bo'ladi, xabar o'zgarmaydi
        # ------------------------------------------------------

    else:  # API da xatolik
        error_detail = api_response.get('detail',
                                        'Noma\'lum xatolik') if api_response else 'Server bilan bog\'lanish xatosi'
        await query.answer(f"Xatolik: {error_detail[:100]}", show_alert=True)


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


async def back_to_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = update.effective_chat.id
    lang_code = get_user_lang(context)
    logger.info(f"User {user_id} requested back to order history.")

    try:
        await query.delete_message()
    except Exception as e:
        logger.warning(f"Could not delete previous message on back_to_history: {e}")

    # "Yuklanmoqda..." xabarini yuborish (foydalanuvchiga feedback uchun)
    loading_text = "Buyurtmalar tarixi yuklanmoqda..." if lang_code == 'uz' else "Загрузка истории заказов..."
    sent_loading_message = await context.bot.send_message(chat_id=chat_id, text=loading_text)

    history_response = await make_api_request(context, 'GET', 'orders/history/', user_id, params={'page': 1})

    final_text = ""
    final_markup = None

    if history_response and not history_response.get('error'):
        orders = history_response.get('results', [])
        count = history_response.get('count', 0)
        next_page_url = history_response.get('next')
        previous_page_url = history_response.get('previous')

        if count == 0:
            final_text = "Sizda hali buyurtmalar mavjud emas." if lang_code == 'uz' else "У вас пока нет заказов."
        else:
            page_title = " (1-sahifa)" if lang_code == 'uz' else " (Страница 1)"
            final_text = f"📋 <b>Buyurtmalar Tarixi{page_title}:</b>\n\n" if lang_code == 'uz' else f"📋 <b>История Заказов{page_title}:</b>\n\n"
            keyboard_list = []
            for order in orders:
                order_id_str = str(order.get('id', 'N/A'))
                status = order.get('status', '')
                status_display = status.replace('_', ' ').capitalize()
                created_at = order.get('created_at', '')
                try:
                    dt_obj = datetime.datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))
                    formatted_date = timezone.localtime(dt_obj).strftime('%Y-%m-%d %H:%M')
                except:
                    formatted_date = str(created_at)[:10]
                total = order.get('total_price', 'N/A')

                final_text += f"🆔 {order_id_str} | {formatted_date} | <i>{status_display}</i> | {total} so'm\n---\n"
                detail_button_text = "Batafsil" if lang_code == 'uz' else "Подробнее"
                keyboard_list.append([InlineKeyboardButton(f"{detail_button_text} (#{order_id_str})",
                                                           callback_data=f"order_{order_id_str}")])

            pagination_row = []
            if previous_page_url:
                try:
                    query_params_prev = parse_qs(urlparse(previous_page_url).query)
                    prev_page = query_params_prev.get('page', [None])[0] or '1'
                    pagination_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"hist_page_{prev_page}"))
                except:
                    pass  # Xatolik bo'lsa tugma qo'shilmaydi
            if next_page_url:
                try:
                    query_params_next = parse_qs(urlparse(next_page_url).query)
                    next_page = query_params_next.get('page', [None])[0]
                    if next_page: pagination_row.append(
                        InlineKeyboardButton("Keyingi ➡️", callback_data=f"hist_page_{next_page}"))
                except:
                    pass
            if pagination_row: keyboard_list.append(pagination_row)
            if keyboard_list: final_markup = InlineKeyboardMarkup(keyboard_list)
    else:
        error_detail = history_response.get('detail', 'API Xatoligi') if history_response else 'Network Xatoligi'
        final_text = f"Tarixni yuklashda xatolik: {error_detail}" if lang_code == 'uz' else f"Ошибка загрузки истории: {error_detail}"
        logger.error(f"Failed to fetch/process history for back_button: {final_text}")

    # "Yuklanmoqda..." xabarini tahrirlaymiz
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id, message_id=sent_loading_message.message_id,
            text=final_text, reply_markup=final_markup, parse_mode=ParseMode.HTML
        )
    except Exception as e:  # Agar tahrirlashda xato bo'lsa (masalan, xabar o'chirilgan bo'lsa)
        logger.error(f"Error editing history message in back_button_callback: {e}", exc_info=True)
        # Yangi xabar yuboramiz
        await context.bot.send_message(chat_id=chat_id, text=final_text, reply_markup=final_markup,
                                       parse_mode=ParseMode.HTML)


async def order_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ "Batafsil" (order_{id}) tugmasi bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()  # Callbackga javob beramiz
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    try:
        if not query.data or not query.data.startswith('order_'): raise ValueError("Invalid callback")
        order_id = int(query.data.split('_')[1])
        logger.info(f"User {user_id} requested details for order {order_id}")

        loading_text = "Buyurtma detallari yuklanmoqda..." if lang_code == 'uz' else "Загрузка деталей заказа..."
        await query.edit_message_text(loading_text)  # Vaqtinchalik xabar

        # API dan buyurtma detallarini olamiz
        order_response = await make_api_request(context, 'GET', f'orders/{order_id}/', user_id)

        if order_response and not order_response.get('error'):
            # Ma'lumotlarni ko'rsatish uchun yordamchi funksiyani chaqiramiz
            await show_order_detail(update, context, order_response)  # <-- show_order_detail ni chaqiramiz
        elif order_response and order_response.get('status_code') == 404:
            not_found_text = "Buyurtma topilmadi." if lang_code == 'uz' else "Заказ не найден."
            await query.edit_message_text(not_found_text)
        else:  # Boshqa API xatoligi
            error_detail = order_response.get('detail', 'N/A') if order_response else 'N/A'
            error_text = f"Buyurtma detallarini olishda xatolik: {error_detail}" if lang_code == 'uz' else f"Ошибка при получении деталей заказа: {error_detail}"
            await query.edit_message_text(error_text)

    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f"Invalid order detail callback: {query.data} - {e}")
        await query.edit_message_text("Xatolik.")


async def history_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Buyurtmalar tarixi sahifalash tugmalari bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()  # Javob beramiz
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    callback_data = query.data  # 'hist_page_{page_num}' yoki 'hist_page_url_{url}'

    logger.info(f"User {user_id} requested history page: {callback_data}")

    endpoint = 'orders/history/'  # Standart endpoint
    params = {}
    page_num_to_log = 'N/A'

    if callback_data.startswith('hist_page_url_'):  # Agar to'liq URL bo'lsa (fallback)
        full_url = callback_data[len('hist_page_url_'):]
        parsed_url = urlparse(full_url)
        endpoint = parsed_url.path.replace('/api/v1/', '', 1)  # API base URL ni olib tashlaymiz
        params = parse_qs(parsed_url.query)
        params = {k: v[0] for k, v in params.items() if len(v) == 1}  # list ni string ga o'giramiz
        page_num_to_log = params.get('page', 'URL')
    elif callback_data.startswith('hist_page_'):  # Agar faqat sahifa raqami bo'lsa
        try:
            page_num = int(callback_data.split('_')[-1])
            params = {'page': page_num}
            page_num_to_log = page_num
        except (ValueError, IndexError, TypeError):
            logger.warning(f"Invalid history page callback data: {callback_data}")
            await query.edit_message_text("Xatolik: Sahifa raqami noto'g'ri.")
            return

    logger.info(f"Fetching history page: {page_num_to_log}")

    # API ga yangi sahifa uchun so'rov yuboramiz
    history_response = await make_api_request(context, 'GET', endpoint, user_id, params=params)

    if history_response and not history_response.get('error'):
        # show_order_history xabarni tahrirlaydi
        await show_order_history(update, context, history_response)
    elif history_response and history_response.get('status_code') == 404:
        await query.answer("Bu sahifa mavjud emas.", show_alert=True)
    else:
        error_detail = history_response.get('detail', 'N/A') if history_response else 'N/A'
        await query.answer(f"Sahifani yuklashda xatolik: {error_detail[:100]}", show_alert=True)


async def cancel_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ "Bekor qilish" (cancel_order_{id}) tugmasi bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer("Bekor qilinmoqda...")
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    try:
        if not query.data or not query.data.startswith('cancel_order_'): raise ValueError("Invalid callback")
        order_id = int(query.data.split('_')[-1])
        logger.info(f"User {user_id} requested cancel for order {order_id}")

        # API ga bekor qilish so'rovini yuboramiz
        api_response = await make_api_request(context, 'POST', f'orders/{order_id}/cancel/', user_id)

        if api_response and not api_response.get('error'):
            # Muvaffaqiyatli bekor qilindi
            success_text = "Buyurtma bekor qilindi." if lang_code == 'uz' else "Заказ отменен."
            await query.answer(success_text, show_alert=True)
            # Buyurtma detallari ko'rinishini yangilaymiz (status o'zgargan bo'lishi kerak)
            updated_order_response = await make_api_request(context, 'GET', f'orders/{order_id}/', user_id)
            if updated_order_response and not updated_order_response.get('error'):
                await show_order_detail(update, context, updated_order_response)  # Yangilangan detallarni ko'rsatamiz
            else:  # Agar yangilangan detalni ololmasak, tarixga qaytaramiz
                await query.edit_message_text("Buyurtma bekor qilindi, lekin yangilangan ma'lumotni olib bo'lmadi.")
                # await show_order_history(update, context, ...) # Yoki tarixni qayta yuklash
        else:  # API xatoligi
            error_detail = api_response.get('detail', api_response.get('error',
                                                                       'Noma\'lum xatolik')) if api_response else 'Server xatosi'
            error_text = f"Bekor qilishda xatolik: {error_detail}" if lang_code == 'uz' else f"Ошибка при отмене: {error_detail}"
            await query.answer(error_text, show_alert=True)

    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f"Invalid cancel order callback: {query.data} - {e}")
        await query.answer("Xatolik!", show_alert=True)


async def branch_location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ "Xaritada ko'rish" (branch_loc_{id}) tugmasi bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    try:
        if not query.data or not query.data.startswith('branch_loc_'): raise ValueError("Invalid callback")
        branch_id = int(query.data.split('_')[-1])
        logger.info(f"User {user_id} requested location for branch ID: {branch_id}")

        # API dan filial detallarini (ayniqsa lat/lon) olamiz
        # Yoki BranchSerializer javobida lat/lon bo'lsa, uni callback_data orqali yuborish ham mumkin
        # Hozircha API dan qayta so'raymiz (agar BranchSerializerda yo'q bo'lsa)
        branch_detail_response = await make_api_request(context, 'GET', f'branches/{branch_id}/',
                                                        user_id)  # Token shart emas

        if branch_detail_response and not branch_detail_response.get('error'):
            branch = branch_detail_response
            latitude = branch.get('latitude')
            longitude = branch.get('longitude')
            branch_name = branch.get('name', 'Filial')

            if latitude is not None and longitude is not None:
                await context.bot.send_message(chat_id=user_id, text=f"📍 {branch_name}:")
                await context.bot.send_location(
                    chat_id=user_id,
                    latitude=latitude,
                    longitude=longitude
                )
            else:
                no_loc_text = "Bu filial uchun lokatsiya kiritilmagan." if lang_code == 'uz' else "Для этого филиала не указана локация."
                await context.bot.send_message(chat_id=user_id, text=no_loc_text)
        else:
            error_detail = branch_detail_response.get('detail', 'N/A') if branch_detail_response else 'N/A'
            error_text = f"Filial ma'lumotini olib bo'lmadi: {error_detail}" if lang_code == 'uz' else f"Не удалось получить данные филиала: {error_detail}"
            await context.bot.send_message(chat_id=user_id, text=error_text)

    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f"Invalid branch location callback: {query.data} - {e}")
        await context.bot.send_message(chat_id=user_id, text="Xatolik.")
