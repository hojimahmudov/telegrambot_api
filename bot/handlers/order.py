# bot/handlers/order.py
import logging
import datetime  # <-- Sanani formatlash uchun (agar show_order_history'dan ko'chirsak)
from urllib.parse import urlparse, parse_qs  # <-- URL parse uchun (agar show_order_history'dan ko'chirsak)

from django.utils import timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from api.models import Order
# Loyihadagi boshqa modullardan importlar
from ..config import ASKING_BRANCH, ASKING_LOCATION, MAIN_MENU, ASKING_DELIVERY_TYPE, ASKING_PAYMENT, \
    ASKING_NOTES, CONFIRMING_LOCATION, SELECTING_ADDRESS_OR_NEW, ASKING_SAVE_NEW_ADDRESS, \
    ENTERING_ADDRESS_NAME  # Kerakli holatlar
from ..keyboards import get_main_menu_markup
from ..utils.helpers import get_user_lang
from ..utils.api_client import make_api_request, reverse_geocode

# Klaviaturani import qilish kerak bo'lishi mumkin (masalan, cancel tugmasi uchun)
# from ..keyboards import ...

logger = logging.getLogger(__name__)


# --- YORDAMCHI FUNKSIYA: Filial tanlashni ko'rsatish ---
# (Bu funksiya logikasi menu_browse.py dagi show_branch_list ga o'xshash bo'lishi mumkin,
#  lekin callback datalari boshqacha bo'ladi: checkout_branch_{id})
async def show_branch_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ochiq filiallar ro'yxatini chiqaradi va tanlashni so'raydi."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang_code = get_user_lang(context)
    query = update.callback_query  # Bu funksiya callbackdan chaqiriladi deb hisoblaymiz

    loading_text = "Filiallar yuklanmoqda..." if lang_code == 'uz' else "Загрузка филиалов..."
    # Tugma bosilganiga javob beramiz
    if query: await query.answer(loading_text[:60])

    # API dan filiallar ro'yxatini olamiz (token shart emas deb hisobladik)
    branch_response = await make_api_request(context, 'GET', 'branches/', user_id)

    keyboard = []
    final_text = "Iltimos, olib ketish uchun OCHIQ filialni tanlang:" if lang_code == 'uz' else "Пожалуйста, выберите ОТКРЫТЫЙ филиал для самовывоза:"

    if branch_response and not branch_response.get('error'):
        branches = branch_response.get('results', [])
        # Faqat ochiq filialarni filtrlaymiz
        open_branches = [b for b in branches if b.get('is_open')]

        if open_branches:
            for branch in open_branches:
                branch_name = branch.get('name', 'N/A')
                branch_id = branch.get('id')
                # Qo'shimcha: Manzilni ham qo'shish mumkin
                # address = branch.get('address', '')
                # button_text = f"{branch_name} ({address[:20]}...)"
                keyboard.append([
                    InlineKeyboardButton(branch_name, callback_data=f"checkout_branch_{branch_id}")
                ])
        else:
            final_text = "Afsuski, hozir ochiq filiallar mavjud emas. Buyurtmani bekor qilishingiz mumkin." if lang_code == 'uz' else "К сожалению, сейчас нет открытых филиалов. Вы можете отменить заказ."
            # Agar ochiq filial bo'lmasa, faqat Bekor qilish tugmasini qoldiramiz

    else:  # API xatoligi
        error_detail = branch_response.get('detail', 'N/A') if branch_response else 'N/A'
        final_text = f"Filiallarni olib bo'lmadi: {error_detail}" if lang_code == 'uz' else f"Не удалось получить филиалы: {error_detail}"

    # Bekor qilish tugmasini har doim qo'shamiz
    cancel_text = "Bekor qilish" if lang_code == 'uz' else "Отмена"
    keyboard.append([InlineKeyboardButton(f"❌ {cancel_text}", callback_data="checkout_cancel")])  # Maxsus callback data
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Oldingi xabarni ("Yetkazib berish turini tanlang:") tahrirlaymiz
    if query:
        try:
            await query.edit_message_text(text=final_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error editing message for branch selection: {e}")
            # Fallback: Send new message
            await context.bot.send_message(chat_id=chat_id, text=final_text, reply_markup=reply_markup,
                                           parse_mode=ParseMode.HTML)
    else:  # Bu holat bo'lmasligi kerak
        await context.bot.send_message(chat_id=chat_id, text=final_text, reply_markup=reply_markup,
                                       parse_mode=ParseMode.HTML)


async def prompt_for_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """To'lov turini so'rash xabarini va tugmalarini yuboradi."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang_code = get_user_lang(context)
    query = update.callback_query  # Ko'pincha callbackdan keladi

    payment_prompt = "To'lov turini tanlang:" if lang_code == 'uz' else "Выберите способ оплаты:"
    cash_text = "💵 Naqd" if lang_code == 'uz' else "💵 Наличные"
    card_text = "💳 Karta" if lang_code == 'uz' else "💳 Картой"
    cancel_text = "❌ Bekor qilish" if lang_code == 'uz' else "❌ Отмена"
    keyboard = [
        [InlineKeyboardButton(cash_text, callback_data="checkout_payment_cash"),
         InlineKeyboardButton(card_text, callback_data="checkout_payment_card")],
        [InlineKeyboardButton(cancel_text, callback_data="checkout_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query and query.message:  # Agar avvalgi xabarni tahrirlash mumkin bo'lsa
        try:
            await query.edit_message_text(text=payment_prompt, reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"Could not edit message to prompt for payment: {e}")
            await context.bot.send_message(chat_id=chat_id, text=payment_prompt, reply_markup=reply_markup)
    elif update.message:  # Agar message handlerdan kelgan bo'lsa (masalan, handle_location)
        await update.message.reply_text(text=payment_prompt, reply_markup=reply_markup)
    else:  # Boshqa holatlar uchun (ehtimol query.message yo'q)
        await context.bot.send_message(chat_id=chat_id, text=payment_prompt, reply_markup=reply_markup)

    return ASKING_PAYMENT


async def prompt_for_address_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Saqlangan manzillarni chiqaradi yoki yangi lokatsiya yuborishni so'raydi."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang_code = get_user_lang(context)
    query = update.callback_query

    loading_text = "Saqlangan manzillar tekshirilmoqda..." if lang_code == 'uz' else "Проверка сохраненных адресов..."
    if query:
        await query.answer()  # Avval callbackga javob beramiz
        try:
            await query.edit_message_text(loading_text)
        except:
            await context.bot.send_message(chat_id=chat_id, text=loading_text)  # Fallback
    else:  # Agar query bo'lmasa (masalan, handle_delivery_type_selection dan to'g'ridan-to'g'ri)
        await context.bot.send_message(chat_id=chat_id, text=loading_text)

    saved_addresses_response = await make_api_request(context, 'GET', 'users/addresses/', user_id)
    keyboard = []
    final_text = ""

    if saved_addresses_response and not saved_addresses_response.get('error'):
        addresses = saved_addresses_response.get('results', [])
        context.user_data['checkout_saved_addresses'] = {addr['id']: addr for addr in addresses}  # Tez qidirish uchun

        if addresses:
            final_text = "Saqlangan manzillardan birini tanlang yoki yangi lokatsiya yuboring:" if lang_code == 'uz' else "Выберите один из сохраненных адресов или отправьте новую локацию:"
            for addr in addresses:
                addr_name = addr.get('name', '')
                addr_text_short = addr.get('address_text', f"Lat: {addr['latitude']:.2f}")[:30]
                display_name = f"{addr_name} ({addr_text_short}...)" if addr_name else addr_text_short
                keyboard.append([InlineKeyboardButton(display_name, callback_data=f"use_saved_addr_{addr.get('id')}")])
        # Agar saqlangan manzil bo'lmasa, final_text bo'sh qoladi, keyingi blok ishlaydi
    else:
        logger.warning(f"Could not fetch saved addresses for user {user_id}: {saved_addresses_response}")
        # Xatolik bo'lsa ham, yangi lokatsiya yuborish imkoniyatini beramiz

    new_loc_text = "📍 Yangi lokatsiya yuborish" if lang_code == 'uz' else "📍 Отправить новую локацию"
    keyboard.append([InlineKeyboardButton(new_loc_text, callback_data="send_new_location")])
    cancel_text = "❌ Bekor qilish" if lang_code == 'uz' else "❌ Отмена"
    keyboard.append([InlineKeyboardButton(cancel_text, callback_data="checkout_cancel")])

    if not final_text:  # Agar saqlangan manzillar bo'lmasa yoki API xatoligi
        final_text = "Iltimos, yetkazib berish manzilini tanlang yoki yangi lokatsiya yuboring:" if lang_code == 'uz' else "Пожалуйста, выберите адрес доставки или отправьте новую локацию:"

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Xabarni tahrirlash yoki yangisini yuborish
    # Bu funksiya callbackdan chaqirilgani uchun query.message mavjud bo'ladi
    if query and query.message:
        try:
            await query.edit_message_text(text=final_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=final_text, reply_markup=reply_markup,
                                           parse_mode=ParseMode.HTML)
    else:  # Bu holat bo'lmasligi kerak, chunki prompt_for_address_selection callbackdan keyin chaqiriladi
        await context.bot.send_message(chat_id=chat_id, text=final_text, reply_markup=reply_markup,
                                       parse_mode=ParseMode.HTML)

    return SELECTING_ADDRESS_OR_NEW


# --- YETKAZIB BERISH TURI TANLOVINI ISHLAYDIGAN HANDLER ---
async def handle_delivery_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    selection = query.data

    if selection == "checkout_set_delivery":
        logger.info(f"User {user_id} selected delivery.")
        context.user_data['checkout_delivery_type'] = 'delivery'
        # --- MANZIL TANLASH/YANGI SO'RASHGA O'TAMIZ ---
        return await prompt_for_address_selection(update, context)
        # -------------------------------------------
    elif selection == "checkout_set_pickup":
        logger.info(f"User {user_id} selected pickup.")
        context.user_data['checkout_delivery_type'] = 'pickup'
        await show_branch_selection(update, context)
        return ASKING_BRANCH
    else:
        logger.warning(f"Unexpected callback data: {selection}")
        return ASKING_DELIVERY_TYPE


async def handle_branch_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Filial tanlash tugmasi ('checkout_branch_{id}') bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    try:
        # Callback datadan filial ID sini olamiz
        if not query.data or not query.data.startswith('checkout_branch_'): raise ValueError("Invalid callback")
        branch_id = int(query.data.split('_')[-1])
        logger.info(f"User {user_id} selected branch ID: {branch_id}")

        # Tanlangan filial ID sini kontekstga saqlaymiz
        context.user_data['checkout_pickup_branch_id'] = branch_id

        # --- Endi To'lov turini so'raymiz ---
        payment_prompt = "To'lov turini tanlang:" if lang_code == 'uz' else "Выберите способ оплаты:"
        cash_text = "💵 Naqd" if lang_code == 'uz' else "💵 Наличные"
        card_text = "💳 Karta" if lang_code == 'uz' else "💳 Картой"
        cancel_text = "❌ Bekor qilish" if lang_code == 'uz' else "❌ Отмена"

        keyboard = [
            [
                InlineKeyboardButton(cash_text, callback_data="checkout_payment_cash"),
                InlineKeyboardButton(card_text, callback_data="checkout_payment_card")
            ],
            [InlineKeyboardButton(cancel_text, callback_data="checkout_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Oldingi xabarni tahrirlab, yangi savolni va tugmalarni chiqaramiz
        await query.edit_message_text(
            text=payment_prompt,
            reply_markup=reply_markup
        )
        # -------------------------------------

        return ASKING_PAYMENT  # To'lov turini kutish holatiga o'tamiz

    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f"Invalid branch selection callback: {query.data} - {e}")
        await query.edit_message_text("Xatolik: Filial tanlashda muammo.")
        # Qaysi holatga qaytish kerak? Avvalgi holatga qaytish qiyin bo'lishi mumkin
        # Yaxshisi suhbatni tugatish yoki ASKING_BRANCH da qolish
        return ASKING_BRANCH  # Shu holatda qolamiz


# --- YANGI: To'lov Turini Tanlashni Boshqaradigan Handler ---
async def handle_payment_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """To'lov turi tugmasi ('checkout_payment_{type}') bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    try:
        # Callback datadan to'lov turini olamiz
        if not query.data or not query.data.startswith('checkout_payment_'): raise ValueError("Invalid callback")
        payment_type = query.data.split('_')[-1]  # 'cash' yoki 'card'
        if payment_type not in ['cash', 'card']: raise ValueError("Invalid payment type")

        logger.info(f"User {user_id} selected payment type: {payment_type}")
        # Tanlangan to'lov turini kontekstga saqlaymiz
        context.user_data['checkout_payment_type'] = payment_type

        # --- Endi Izoh qoldirishni so'raymiz ---
        notes_prompt = "Buyurtmaga qo'shimcha izohingiz bormi? (Ixtiyoriy)\n\nYozmasangiz pastdagi tugmani bosing." \
            if lang_code == 'uz' else \
            "Есть ли у вас дополнительные комментарии к заказу? (Необязательно)\n\nНажмите кнопку ниже, если нет."
        skip_text = "➡️ Keyingisi / Izohsiz" if lang_code == 'uz' else "➡️ Далее / Без комментария"
        keyboard = [[InlineKeyboardButton(skip_text, callback_data="checkout_skip_notes")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Oldingi xabarni tahrirlaymiz
        await query.edit_message_text(
            text=notes_prompt,
            reply_markup=reply_markup
        )
        # --------------------------------------

        return ASKING_NOTES  # Izoh kutish holatiga o'tamiz

    except (IndexError, ValueError, TypeError) as e:
        logger.warning(f"Invalid payment selection callback: {query.data} - {e}")
        await query.edit_message_text("Xatolik: To'lov turini tanlashda muammo.")
        return ASKING_PAYMENT  # Shu holatda qolamiz


# --- YANGI: Yakuniy Checkout Uchun Yordamchi Funksiya ---
async def finalize_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ma'lumotlarni yig'adi, checkout API ni chaqiradi, natijani yuboradi, suhbatni tugatadi."""
    query = update.callback_query
    message = update.message
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang_code = get_user_lang(context)
    message_to_edit_id = query.message.message_id if query and query.message else None

    processing_text = "Buyurtma rasmiylashtirilmoqda, iltimos kuting..." if lang_code == 'uz' else "Обработка заказа, пожалуйста подождите..."
    sent_processing_message = None
    if message_to_edit_id:
        try:
            # Oldingi xabarni tahrirlash o'rniga, uni o'chirib, yangi xabar yuboramiz,
            # chunki oxirida bir nechta xabar (matn + lokatsiya) yuborishimiz mumkin.
            await context.bot.delete_message(chat_id=chat_id, message_id=message_to_edit_id)
            sent_processing_message = await context.bot.send_message(chat_id=chat_id, text=processing_text)
        except Exception as e:
            logger.warning(f"Could not edit/delete processing message: {e}")
            sent_processing_message = await context.bot.send_message(chat_id=chat_id, text=processing_text)
    elif message:
        await message.reply_text(processing_text)  # Yangi xabar yuboramiz
    else:
        sent_processing_message = await context.bot.send_message(chat_id=chat_id, text=processing_text)

    # Checkout ma'lumotlarini yig'amiz (avvalgidek)
    # ... (checkout_data ni yig'ish va validatsiya qilish kodi #199-javobdan olinadi) ...
    delivery_type = context.user_data.get("checkout_delivery_type")
    payment_type = context.user_data.get("checkout_payment_type")
    notes = context.user_data.get("checkout_notes", "")
    if not delivery_type or not payment_type:  # Eng oddiy validatsiya
        logger.error(f"Missing critical checkout data for user {user_id}")
        # ... (Xatolik xabarini yuborib, suhbatni tugatish) ...
        return ConversationHandler.END

    checkout_data = {"delivery_type": delivery_type, "payment_type": payment_type, "notes": notes, }
    if delivery_type == 'delivery':
        latitude = context.user_data.get("checkout_latitude");
        longitude = context.user_data.get("checkout_longitude")
        if latitude is None or longitude is None: return ConversationHandler.END  # Xatolik
        checkout_data['latitude'] = latitude;
        checkout_data['longitude'] = longitude
        if context.user_data.get("checkout_address"): checkout_data['address'] = context.user_data["checkout_address"]
    elif delivery_type == 'pickup':
        branch_id = context.user_data.get("checkout_pickup_branch_id")
        if not branch_id: return ConversationHandler.END  # Xatolik
        checkout_data['pickup_branch_id'] = branch_id
    # ------------------------------------------------------------

    logger.info(f"Final checkout data for user {user_id}: {checkout_data}")
    api_response = await make_api_request(context, 'POST', 'orders/checkout/', user_id, data=checkout_data)

    final_message = ""
    final_markup = get_main_menu_markup(context)
    branch_location_to_send = None

    # Processing xabarini o'chiramiz (agar yuborilgan bo'lsa)
    if sent_processing_message:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=sent_processing_message.message_id)
        except Exception:
            pass

    if api_response and api_response.get('status_code') == 201 and not api_response.get('error'):
        order_data = api_response  # Endi bu to'liq buyurtma ma'lumoti
        print(f"\n\n{order_data}\n\n")
        order_id = order_data.get('id')
        status_choices = dict(
            Order.STATUS_CHOICES)  # Modeldan status nomlarini olish (agar model import qilingan bo'lsa)
        # Yoki API javobida tayyor nomi kelsa, shuni ishlatamiz
        status_display = order_data.get('status', 'N/A')  # Hozircha API dan kelgan kodni ishlatamiz
        total = order_data.get('total_price')
        delivery_type = order_data.get('delivery_type')
        pickup_branch_data = order_data.get('pickup_branch')  # Nested filial ma'lumoti
        est_ready_iso = order_data.get('estimated_ready_at')
        est_delivery_iso = order_data.get('estimated_delivery_at')

        # --- Yakuniy Xabarni Formatlash ---
        if lang_code == 'uz':
            final_message = f"✅ Buyurtmangiz <b>#{order_id}</b> muvaffaqiyatli rasmiylashtirildi!\n\n"
            final_message += f"Holati: <i>{status_display}</i>\n"  # Statusni qo'shamiz
            final_message += f"Umumiy summa: <b>{total}</b> so'm\n"
            # Buyurtma tarkibini ham qo'shish mumkin (agar OrderSerializer 'items'ni qaytarsa)
            items = order_data.get('items', [])
            if items:
                final_message += "\nTarkibi:\n"
                for item in items:
                    prod_name = item.get('product', {}).get('name', '?')
                    qty = item.get('quantity')
                    price = item.get('total_price')
                    final_message += f"- {prod_name} x {qty} ({price} so'm)\n"

            # Yetkazib berish/olib ketish ma'lumotlari
            if delivery_type == 'pickup' and pickup_branch_data:
                branch_name = pickup_branch_data.get('name', 'N/A')
                branch_address = pickup_branch_data.get('address', 'N/A')
                final_message += f"\n<b>Olib ketish manzili:</b>\n📍 {branch_name}\n<pre>{branch_address}</pre>\n"  # Manzilni <pre> ichida
                lat = pickup_branch_data.get('latitude')
                lon = pickup_branch_data.get('longitude')
                if lat is not None and lon is not None:
                    branch_location_to_send = (lat, lon)
            else:  # Delivery
                # Manzilni API javobidan olish (agar saqlangan bo'lsa)
                delivery_address = order_data.get('address')
                if delivery_address:
                    final_message += f"\n<b>Yetkazib berish manzili:</b>\n<pre>{delivery_address}</pre>\n"
                # Yoki shunchaki:
                # final_message += f"Buyurtmangiz ko'rsatilgan manzilga yetkaziladi.\n"

            # Taxminiy vaqtlar
            try:
                if est_ready_iso:
                    dt_obj = datetime.datetime.fromisoformat(str(est_ready_iso).replace('Z', '+00:00'))
                    # Vaqtni lokal vaqtga o'tkazish uchun pytz yoki Django timezone kerak
                    # Hozircha oddiy formatlash:
                    ready_time_str = dt_obj.strftime('%H:%M')  # Yoki timezone.localtime(dt_obj).strftime('%H:%M')
                    final_message += f"\nTaxminiy tayyor bo'lish vaqti: ~{ready_time_str}\n"
                if est_delivery_iso:
                    dt_obj = datetime.datetime.fromisoformat(str(est_delivery_iso).replace('Z', '+00:00'))
                    delivery_time_str = dt_obj.strftime('%H:%M')  # Yoki timezone.localtime(dt_obj).strftime('%H:%M')
                    final_message += f"Taxminiy yetkazib berish vaqti: ~{delivery_time_str}\n"
            except Exception as time_e:
                logger.error(f"Error formatting time in final msg: {time_e}")

        else:  # Russian Language
            final_message = f"✅ Ваш заказ <b>#{order_id}</b> успешно оформлен!\n\n"
            final_message += f"Статус: <i>{status_display}</i>\n"
            final_message += f"Итоговая сумма: <b>{total}</b> сум\n"
            items = order_data.get('items', [])
            if items:
                final_message += "\nСостав:\n"
                for item in items:
                    prod_name = item.get('product', {}).get('name', '?')
                    qty = item.get('quantity')
                    price = item.get('total_price')
                    final_message += f"- {prod_name} x {qty} ({price} сум)\n"

            if delivery_type == 'pickup' and pickup_branch_data:
                branch_name = pickup_branch_data.get('name', 'N/A')
                branch_address = pickup_branch_data.get('address', 'N/A')
                final_message += f"\n<b>Адрес для самовывоза:</b>\n📍 {branch_name}\n<pre>{branch_address}</pre>\n"
                lat = pickup_branch_data.get('latitude')
                lon = pickup_branch_data.get('longitude')
                if lat is not None and lon is not None:
                    branch_location_to_send = (lat, lon)
            else:
                delivery_address = order_data.get('address')
                if delivery_address:
                    final_message += f"\n<b>Адрес доставки:</b>\n<pre>{delivery_address}</pre>\n"
                # else: final_message += f"Заказ будет доставлен на указанный адрес.\n"

            try:  # Estimated times
                if est_ready_iso:
                    dt_obj = datetime.datetime.fromisoformat(str(est_ready_iso).replace('Z', '+00:00'))
                    ready_time_str = dt_obj.strftime('%H:%M')  # Format time
                    final_message += f"\nПримерное время готовности: ~{ready_time_str}\n"
                if est_delivery_iso:
                    dt_obj = datetime.datetime.fromisoformat(str(est_delivery_iso).replace('Z', '+00:00'))
                    delivery_time_str = dt_obj.strftime('%H:%M')  # Format time
                    final_message += f"Примерное время доставки: ~{delivery_time_str}\n"
            except Exception as time_e:
                logger.error(f"Error formatting time in final msg: {time_e}")
        # -----------------------------------------

    else:  # API Error
        error_detail = api_response.get('detail',
                                        'Noma\'lum xatolik') if api_response else 'Server bilan bog\'lanish xatosi'
        logger.error(f"Checkout API error for user {user_id}: {error_detail}")
        final_message = f"❌ Buyurtmani rasmiylashtirishda xatolik: {str(error_detail)[:100]}"
        # Xatolik bo'lsa ham asosiy menyuga qaytaramiz
        final_markup = get_main_menu_markup(context)

    # --- Yakuniy xabarlarni yuborish ---
    await context.bot.send_message(
        chat_id=chat_id,
        text=final_message,
        reply_markup=final_markup,  # Asosiy menyu klaviaturasini chiqaradi
        parse_mode=ParseMode.HTML  # HTML formatlash uchun
    )

    # Agar olib ketish bo'lsa va lokatsiya bo'lsa, uni alohida yuboramiz
    if branch_location_to_send:
        try:
            await context.bot.send_message(chat_id=chat_id,
                                           text="Filial manzili xaritada:" if lang_code == 'uz' else "Адрес филиала на карте:")
            await context.bot.send_location(
                chat_id=chat_id,
                latitude=branch_location_to_send[0],
                longitude=branch_location_to_send[1]
            )
        except Exception as loc_e:
            logger.error(f"Failed to send branch location for order {order_id}: {loc_e}")
    # -----------------------------

    # Checkout kontekstini tozalaymiz
    keys_to_clear = ['checkout_delivery_type', 'checkout_pickup_branch_id', 'checkout_latitude', 'checkout_longitude',
                     'checkout_payment_type', 'checkout_notes', 'checkout_address']
    for key in keys_to_clear:
        if key in context.user_data:
            try:
                del context.user_data[key]
            except KeyError:
                pass

    return ConversationHandler.END  # Suhbatni tugatib, asosiy menyu holatiga qaytamiz


# --- YANGI: Izoh Kiritish Uchun Handler ---
async def handle_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Foydalanuvchi izoh yozganda ishlaydi."""
    user = update.effective_user
    user_id = user.id
    note_text = update.message.text
    lang_code = get_user_lang(context)
    logger.info(f"User {user_id} entered note: {note_text[:50]}...")

    # Izohni saqlaymiz
    context.user_data['checkout_notes'] = note_text

    # Checkoutni yakunlaymiz
    return await finalize_checkout(update, context)


# --- YANGI: Izohni O'tkazib Yuborish Uchun Callback Handler ---
async def skip_notes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """ "Keyingisi / Izohsiz" tugmasi bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    logger.info(f"User {user_id} skipped notes.")

    # Izoh maydonini bo'sh qoldiramiz
    context.user_data['checkout_notes'] = ""

    # Checkoutni yakunlaymiz
    return await finalize_checkout(update, context)


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    message = update.message
    location = message.location
    user_id = update.effective_user.id
    lang_code = get_user_lang(context)

    if location:
        lat = location.latitude
        lon = location.longitude
        logger.info(f"User {user_id} sent location: Lat {lat}, Lon {lon}")

        # --- REVERSE GEOCODING ---
        address_text = await reverse_geocode(lat, lon)
        # -------------------------

        if address_text:
            # Saqlab qo'yish uchun vaqtinchalik ma'lumotlar
            context.user_data['checkout_pending_latitude'] = lat
            context.user_data['checkout_pending_longitude'] = lon
            context.user_data['checkout_pending_address_text'] = address_text  # Matnli manzilni ham saqlaymiz

            confirm_prompt = "📍 Siz yuborgan manzil:\n" if lang_code == 'uz' else "📍 Вы отправили адрес:\n"
            confirm_prompt += f"<pre>{address_text}</pre>\n\n"
            confirm_prompt += "Ushbu manzil to'g'rimi?" if lang_code == 'uz' else "Этот адрес правильный?"

            yes_text = "✅ Ha" if lang_code == 'uz' else "✅ Да"
            no_text = "❌ Yo'q, qayta yuborish" if lang_code == 'uz' else "❌ Нет, отправить заново"
            cancel_text = "🚫 Bekor qilish" if lang_code == 'uz' else "🚫 Отмена"

            keyboard = [
                [
                    InlineKeyboardButton(yes_text, callback_data="loc_confirm_yes"),
                    InlineKeyboardButton(no_text, callback_data="loc_confirm_no")
                ],
                [InlineKeyboardButton(cancel_text, callback_data="checkout_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await message.reply_text(confirm_prompt, reply_markup=reply_markup,
                                     parse_mode=ParseMode.HTML)  # ReplyKeyboardRemove
            return CONFIRMING_LOCATION  # Tasdiqlashni kutish holati
        else:
            # Agar reverse geocoding ishlamasa
            error_text = "Lokatsiyangizni aniqlay olmadim. Iltimos, boshqa joydan yoki aniqroq lokatsiya yuboring, yoki /cancel bosing." if lang_code == 'uz' else "Не удалось определить ваш адрес. Пожалуйста, отправьте более точную локацию или нажмите /cancel."
            await message.reply_text(error_text)
            return ASKING_LOCATION  # Shu holatda qolamiz
    else:  # Bu holat bo'lmasligi kerak (filtr tufayli)
        logger.warning(f"Location handler triggered for user {user_id} but no location found.")
        return ASKING_LOCATION


async def confirm_location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    selection = query.data

    if selection == "loc_confirm_yes":
        logger.info(f"User {user_id} confirmed new location.")
        # Vaqtinchalik saqlangan lokatsiya va manzilni asosiy checkout ma'lumotlariga o'tkazamiz
        # Bu ma'lumotlar 'checkout_pending_...' kalitlarida saqlangan edi
        context.user_data['checkout_latitude'] = context.user_data.get('checkout_pending_latitude')
        context.user_data['checkout_longitude'] = context.user_data.get('checkout_pending_longitude')
        context.user_data['checkout_address'] = context.user_data.get('checkout_pending_address_text')

        # Endi bu yangi manzilni saqlashni so'raymiz
        save_prompt = "Bu yangi manzilni keyingi buyurtmalar uchun saqlab qolishni xohlaysizmi?" if lang_code == 'uz' else "Хотите сохранить этот новый адрес для будущих заказов?"
        yes_save_text = "✅ Ha, saqlash" if lang_code == 'uz' else "✅ Да, сохранить"
        no_save_text = "❌ Yo'q, shart emas" if lang_code == 'uz' else "❌ Нет, не нужно"

        keyboard = [
            [InlineKeyboardButton(yes_save_text, callback_data="save_new_addr_yes")],
            [InlineKeyboardButton(no_save_text, callback_data="save_new_addr_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=save_prompt, reply_markup=reply_markup)
        return ASKING_SAVE_NEW_ADDRESS  # Yangi holatga o'tamiz

    elif selection == "loc_confirm_no":
        # ... (Qayta manzil so'rash logikasi avvalgidek - prompt_for_address_selection chaqiradi) ...
        logger.info(f"User {user_id} rejected location, prompting for address selection or new.")
        return await prompt_for_address_selection(update, context)  # Bu funksiya o'zining state'ini qaytaradi
    else:
        return CONFIRMING_LOCATION


async def handle_save_new_address_decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    selection = query.data  # "save_new_addr_yes" yoki "save_new_addr_no"

    if selection == "save_new_addr_yes":
        logger.info(f"User {user_id} chose to save the new address.")
        # Manzil uchun nom so'raymiz
        prompt_name_text = "Manzil uchun nom kiriting (masalan, 'Uy', 'Ish').\nBo'sh qoldirsangiz, manzilning bir qismi nom bo'ladi.\n/skip_address_name - nom bermaslik." \
            if lang_code == 'uz' else \
            "Введите название для адреса (например, 'Дом', 'Работа').\nЕсли оставить пустым, частью адреса будет название.\n/skip_address_name - не указывать название."

        # Biz ForceReply ishlatishimiz mumkin yoki oddiy matn kutishimiz mumkin
        # Hozircha oddiy matn kutamiz va /skip_address_name buyrug'ini qo'shamiz
        # Yoki inline tugma bilan "Nom bermaslik"
        skip_btn_text = "Nom bermasdan saqlash" if lang_code == 'uz' else "Сохранить без названия"
        keyboard = [[InlineKeyboardButton(skip_btn_text, callback_data="save_addr_skip_name")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(text=prompt_name_text, reply_markup=reply_markup)
        return ENTERING_ADDRESS_NAME  # Manzil nomini kutish holati

    elif selection == "save_new_addr_no":
        logger.info(f"User {user_id} chose NOT to save the new address.")
        # Vaqtinchalik pending ma'lumotlarni tozalaymiz (chunki ular endi 'checkout_latitude' ga o'tdi)
        for key in ['checkout_pending_latitude', 'checkout_pending_longitude', 'checkout_pending_address_text']:
            if key in context.user_data: del context.user_data[key]
        # To'g'ridan-to'g'ri to'lov turini so'rashga o'tamiz
        return await prompt_for_payment(update, context)  # Bu ASKING_PAYMENT qaytaradi
    else:
        return ASKING_SAVE_NEW_ADDRESS  # Kutilmagan holat


async def handle_address_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Foydalanuvchi yangi manzil uchun nom yozganda ishlaydi."""
    user = update.effective_user  # Bu MessageHandler bo'lgani uchun update.message bor
    user_id = user.id
    address_name_input = update.message.text
    lang_code = get_user_lang(context)

    logger.info(f"User {user_id} entered address name: {address_name_input[:30]}")
    context.user_data['checkout_new_address_name'] = address_name_input

    # Endi manzilni API ga saqlaymiz va keyin to'lovga o'tamiz
    return await save_newly_confirmed_address(update, context)


async def skip_address_name_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """ "Nom bermaslik" tugmasi bosilganda yoki /skip_address_name buyrug'i kelganda."""
    query = update.callback_query
    if query: await query.answer()

    user_id = update.effective_user.id
    logger.info(f"User {user_id} chose to skip address name.")
    context.user_data['checkout_new_address_name'] = None  # Nom yo'q

    # Endi manzilni API ga saqlaymiz va keyin to'lovga o'tamiz
    return await save_newly_confirmed_address(update, context)


async def save_newly_confirmed_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Tasdiqlangan yangi manzilni APIga yuboradi va keyin to'lovga o'tadi."""
    user_id = update.effective_user.id
    lang_code = get_user_lang(context)
    query = update.callback_query  # skip_notes_callback dan kelishi mumkin

    lat = context.user_data.get('checkout_latitude')  # Bular loc_confirm_yes da o'rnatilgan edi
    lon = context.user_data.get('checkout_longitude')
    addr_text = context.user_data.get('checkout_address')
    addr_name = context.user_data.get('checkout_new_address_name')  # Yangi nom

    if lat is None or lon is None:
        logger.error(f"Cannot save address for user {user_id}, lat/lon missing from context.")
        await context.bot.send_message(chat_id=user_id, text="Manzilni saqlashda xatolik (koordinatalar yo'q).")
        return await prompt_for_payment(update, context)  # To'lovga o'tib ketamiz

    address_payload = {
        "latitude": lat,
        "longitude": lon,
        "address_text": addr_text,
        "name": addr_name if addr_name else None  # Agar nom berilmagan bo'lsa None
    }
    logger.info(f"Saving new address to API for user {user_id}: {address_payload}")
    api_response = await make_api_request(context, 'POST', 'users/addresses/', user_id, data=address_payload)

    if api_response and not api_response.get('error') and api_response.get('status_code') == 201:
        save_success_text = "✅ Yangi manzil saqlandi!" if lang_code == 'uz' else "✅ Новый адрес сохранен!"
        if query:  # Agar tugma bosilgan bo'lsa (skip name)
            await query.answer(save_success_text)
        else:  # Agar nom yozilgan bo'lsa (handle_address_name_input)
            await context.bot.send_message(chat_id=user_id, text=save_success_text)
    else:
        save_fail_text = "Manzilni saqlashda xatolik yuz berdi." if lang_code == 'uz' else "Произошла ошибка при сохранении адреса."
        logger.warning(f"Failed to save new address for user {user_id}. API response: {api_response}")
        if query:
            await query.answer(save_fail_text, show_alert=True)
        else:
            await context.bot.send_message(chat_id=user_id, text=save_fail_text)

    # Vaqtinchalik pending va nom ma'lumotlarini tozalaymiz
    for key in ['checkout_pending_latitude', 'checkout_pending_longitude', 'checkout_pending_address_text',
                'checkout_new_address_name']:
        if key in context.user_data: del context.user_data[key]

    return await prompt_for_payment(update, context)


async def show_order_history(update: Update, context: ContextTypes.DEFAULT_TYPE, history_data: dict):
    """API dan kelgan buyurtmalar tarixi ma'lumotlarini formatlab ko'rsatadi."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang_code = get_user_lang(context)

    orders = history_data.get('results', [])
    count = history_data.get('count', 0)
    next_page_url = history_data.get('next')
    previous_page_url = history_data.get('previous')

    message_to_edit = update.callback_query.message if update.callback_query else None

    if count == 0:
        history_empty_text = "Sizda hali buyurtmalar mavjud emas." if lang_code == 'uz' else "У вас пока нет заказов."
        try:
            if message_to_edit:
                await update.callback_query.edit_message_text(history_empty_text, reply_markup=None)
            elif update.message:
                await update.message.reply_text(history_empty_text)
        except Exception as e:
            logger.warning(f"Could not edit/send empty history message: {e}")
        return

    message_text = "📋 **Buyurtmalar Tarixi:**\n\n" if lang_code == 'uz' else "📋 **История Заказов:**\n\n"
    keyboard = []  # Inline tugmalar uchun

    for order in orders:
        order_id = order.get('id')
        status = order.get('status', '')
        # Statusni chiroyliroq chiqarish (agar kerak bo'lsa, alohida funksiya qilish mumkin)
        status_display = status  # Hozircha kodini o'zini chiqaramiz
        created_at = order.get('created_at', '')
        # Sanani formatlash (agar kerak bo'lsa)
        try:  # Vaqtni formatlashga harakat qilamiz
            dt_obj = datetime.datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            formatted_date = dt_obj.strftime('%Y-%m-%d %H:%M')
        except:
            formatted_date = created_at[:10]  # Agar formatlash xato bo'lsa, faqat sanani olamiz

        total = order.get('total_price', 'N/A')

        message_text += f"🆔 {order_id} | {formatted_date} | {status_display} | {total} so'm\n"
        # Har bir buyurtma uchun "Batafsil" tugmasi
        detail_button_text = "Batafsil" if lang_code == 'uz' else "Подробнее"
        keyboard.append([InlineKeyboardButton(f"{detail_button_text} ({order_id})", callback_data=f"order_{order_id}")])
        message_text += "---\n"

    # Paginatsiya tugmalari
    pagination_row = []
    if previous_page_url:
        # URL dan page raqamini olishga harakat qilamiz (agar ?page=X bo'lsa)
        try:
            query_params = parse_qs(urlparse(previous_page_url).query)
            prev_page = query_params.get('page', [None])[0]
            if prev_page:
                pagination_row.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"hist_page_{prev_page}"))
            else:  # Agar page topilmasa, to'liq URL ishlatamiz (xavfliroq)
                pagination_row.append(
                    InlineKeyboardButton("⬅️ Oldingi", callback_data=f"hist_page_url_{previous_page_url}"))
        except:  # Agar URL parse qilishda xato bo'lsa
            pagination_row.append(
                InlineKeyboardButton("⬅️ Oldingi", callback_data=f"hist_page_url_{previous_page_url}"))

    if next_page_url:
        try:
            query_params = parse_qs(urlparse(next_page_url).query)
            next_page = query_params.get('page', [None])[0]
            if next_page:
                pagination_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"hist_page_{next_page}"))
            else:
                pagination_row.append(
                    InlineKeyboardButton("Keyingi ➡️", callback_data=f"hist_page_url_{next_page_url}"))
        except:
            pagination_row.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"hist_page_url_{next_page_url}"))

    if pagination_row:
        keyboard.append(pagination_row)

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    # Xabarni yuborish yoki tahrirlash
    try:
        if message_to_edit:
            await update.callback_query.edit_message_text(text=message_text, reply_markup=reply_markup,
                                                          parse_mode=ParseMode.HTML)  # Yoki MarkdownV2
        elif update.message:
            await update.message.reply_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error sending/editing order history: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Buyurtmalar tarixini ko'rsatishda xatolik.")


async def show_order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, order_data: dict):
    """API dan kelgan yagona buyurtma ma'lumotlarini formatlab chiqaradi."""
    query = update.callback_query  # Bu funksiya callbackdan chaqiriladi
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    lang_code = get_user_lang(context)

    order_id = order_data.get('id', 'N/A')
    status = order_data.get('status', '')
    # TODO: Status kodini chiroyli nomga o'girish
    status_display = status.replace('_', ' ').capitalize()  # Oddiy formatlash
    created_at_iso = order_data.get('created_at', '')
    total_price = order_data.get('total_price', 'N/A')
    delivery_type = order_data.get('delivery_type')
    payment_type = order_data.get('payment_type')  # TODO: Buni ham chiroyli nomga o'girish
    notes = order_data.get('notes', '')
    items = order_data.get('items', [])
    pickup_branch_data = order_data.get('pickup_branch')
    address = order_data.get('address')
    latitude = order_data.get('latitude')
    longitude = order_data.get('longitude')
    est_ready_iso = order_data.get('estimated_ready_at')
    est_delivery_iso = order_data.get('estimated_delivery_at')

    # Sanani formatlash
    formatted_date = ''
    try:
        dt_obj = datetime.datetime.fromisoformat(str(created_at_iso).replace('Z', '+00:00'))
        formatted_date = timezone.localtime(dt_obj).strftime('%Y-%m-%d %H:%M')
    except:
        formatted_date = str(created_at_iso)[:10]

    # Xabar matnini yaratamiz (HTML)
    message_text = f"📄 <b>Buyurtma #{order_id} Tafsilotlari</b>\n\n" if lang_code == 'uz' else f"📄 <b>Детали Заказа #{order_id}</b>\n\n"
    message_text += f"<b>Holati:</b> <i>{status_display}</i>\n" if lang_code == 'uz' else f"<b>Статус:</b> <i>{status_display}</i>\n"
    message_text += f"<b>Sana:</b> {formatted_date}\n" if lang_code == 'uz' else f"<b>Дата:</b> {formatted_date}\n"
    message_text += f"<b>To'lov turi:</b> {payment_type}\n" if lang_code == 'uz' else f"<b>Тип оплаты:</b> {payment_type}\n"  # TODO: Tarjima

    if delivery_type == 'pickup' and pickup_branch_data:
        branch_name = pickup_branch_data.get('name', 'N/A')
        branch_address = pickup_branch_data.get('address', 'N/A')
        message_text += f"<b>Olib ketish filiali:</b> {branch_name}\n<pre>{branch_address}</pre>\n" if lang_code == 'uz' else f"<b>Филиал самовывоза:</b> {branch_name}\n<pre>{branch_address}</pre>\n"
    elif delivery_type == 'delivery':
        if address:
            message_text += f"<b>Yetkazish manzili:</b>\n<pre>{address}</pre>\n" if lang_code == 'uz' else f"<b>Адрес доставки:</b>\n<pre>{address}</pre>\n"
        elif latitude and longitude:
            message_text += f"<b>Yetkazish lokatsiyasi:</b> Lat: {latitude}, Lon: {longitude}\n" if lang_code == 'uz' else f"<b>Локация доставки:</b> Lat: {latitude}, Lon: {longitude}\n"

    # Taxminiy vaqtlar
    try:
        if est_ready_iso:
            dt_obj = datetime.datetime.fromisoformat(str(est_ready_iso).replace('Z', '+00:00'))
            ready_time_str = timezone.localtime(dt_obj).strftime('%H:%M')
            message_text += f"Taxminiy tayyor bo'lish vaqti: ~{ready_time_str}\n" if lang_code == 'uz' else f"Примерное время готовности: ~{ready_time_str}\n"
        if est_delivery_iso:
            dt_obj = datetime.datetime.fromisoformat(str(est_delivery_iso).replace('Z', '+00:00'))
            delivery_time_str = timezone.localtime(dt_obj).strftime('%H:%M')
            message_text += f"Taxminiy yetkazib berish vaqti: ~{delivery_time_str}\n" if lang_code == 'uz' else f"Примерное время доставки: ~{delivery_time_str}\n"
    except Exception as time_e:
        logger.error(f"Error formatting time in detail msg: {time_e}")

    if notes:
        message_text += f"\n<b>Izohlar:</b>\n<pre>{notes}</pre>\n" if lang_code == 'uz' else f"\n<b>Комментарии:</b>\n<pre>{notes}</pre>\n"

    # Mahsulotlar ro'yxati
    if items:
        message_text += "\n<b>Tarkibi:</b>\n" if lang_code == 'uz' else "\n<b>Состав:</b>\n"
        for item in items:
            prod_name = item.get('product', {}).get('name', '?')
            qty = item.get('quantity')
            price_unit = item.get('price_per_unit', 'N/A')
            item_total = item.get('total_price', 'N/A')
            message_text += f"- {prod_name} ({qty} x {price_unit} = {item_total} so'm)\n"  # Narxni formatlash mumkin

    message_text += f"\n<b>Jami: {total_price} so'm</b>" if lang_code == 'uz' else f"\n<b>Итого: {total_price} сум</b>"

    # Tugmalarni yaratamiz
    keyboard = []
    # Agar status 'new' bo'lsa, bekor qilish tugmasini qo'shamiz
    if status == 'new':
        cancel_btn_text = "❌ Bekor qilish" if lang_code == 'uz' else "❌ Отменить заказ"
        keyboard.append([InlineKeyboardButton(cancel_btn_text, callback_data=f"cancel_order_{order_id}")])

    # Ortga qaytish tugmasi
    back_btn_text = "< Ortga (Tarix)" if lang_code == 'uz' else "< Назад (История)"
    keyboard.append([InlineKeyboardButton(back_btn_text, callback_data="back_to_history")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Xabarni tahrirlaymiz
    try:
        await query.edit_message_text(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.error(f"Error editing order detail message: {e}")
        # Eski xabarni o'chirib, yangisini yuborishga harakat qilamiz
        try:
            await query.delete_message()
        except:
            pass
        await context.bot.send_message(chat_id=chat_id, text=message_text, reply_markup=reply_markup,
                                       parse_mode=ParseMode.HTML)


async def handle_saved_address_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Saqlangan manzil tugmasi ('use_saved_addr_{id}') bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    try:
        address_id = int(query.data.split('_')[-1])
        saved_addresses_dict = context.user_data.get('checkout_saved_addresses', {})
        selected_address = saved_addresses_dict.get(address_id)

        if not selected_address:
            logger.warning(f"Selected saved address ID {address_id} not found in context for user {user_id}.")
            await query.edit_message_text("Xatolik: Saqlangan manzil topilmadi. Qaytadan urinib ko'ring.")
            return SELECTING_ADDRESS_OR_NEW

        # Tanlangan manzil ma'lumotlarini checkout uchun asosiy joyga ko'chiramiz
        context.user_data['checkout_latitude'] = selected_address.get('latitude')
        context.user_data['checkout_longitude'] = selected_address.get('longitude')
        context.user_data['checkout_address'] = selected_address.get('address_text') or selected_address.get('name')
        logger.info(f"User {user_id} selected saved address: {context.user_data['checkout_address']}")

        # Vaqtinchalik saqlangan manzillar ro'yxatini tozalaymiz
        if 'checkout_saved_addresses' in context.user_data: del context.user_data['checkout_saved_addresses']

        return await prompt_for_payment(update, context)  # To'lov turini so'rashga o'tamiz

    except (IndexError, ValueError, TypeError, KeyError) as e:
        logger.error(f"Error processing saved address selection: {query.data}, Error: {e}", exc_info=True)
        await query.edit_message_text("Xatolik: Manzilni tanlashda muammo.")
        return SELECTING_ADDRESS_OR_NEW


async def handle_send_new_location_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """ "Yangi lokatsiya yuborish" tugmasi bosilganda."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    logger.info(f"User {user_id} chose to send a new location.")
    message_text = "Iltimos, yetkazib berish manzilini lokatsiya tugmasi orqali yuboring:" if lang_code == 'uz' else "Пожалуйста, отправьте адрес доставки с помощью кнопки геолокации:"

    # Eskicha ReplyKeyboard bilan lokatsiya so'raymiz
    loc_button_text = "📍 Lokatsiya yuborish" if lang_code == 'uz' else "📍 Отправить локацию"
    keyboard = [[KeyboardButton(loc_button_text, request_location=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    try:
        await query.edit_message_text(text=message_text)  # Inline tugmalarni olib tashlaydi
    except Exception as e:
        logger.warning(f"Could not edit 'send new location' prompt: {e}")
        await context.bot.send_message(chat_id=user_id, text=message_text)  # Yangisini yuboramiz

    await context.bot.send_message(chat_id=user_id, text="👇", reply_markup=reply_markup)  # ReplyKeyboardni chiqarish

    return ASKING_LOCATION  # Lokatsiya kutish holati
