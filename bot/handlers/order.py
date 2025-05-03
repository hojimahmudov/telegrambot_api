# bot/handlers/order.py
import logging
import datetime  # <-- Sanani formatlash uchun (agar show_order_history'dan ko'chirsak)
from urllib.parse import urlparse, parse_qs  # <-- URL parse uchun (agar show_order_history'dan ko'chirsak)

from django.utils import timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

# Loyihadagi boshqa modullardan importlar
from ..config import ASKING_BRANCH, ASKING_LOCATION, MAIN_MENU, ASKING_DELIVERY_TYPE, ASKING_PAYMENT, \
    ASKING_NOTES  # Kerakli holatlar
from ..keyboards import get_main_menu_markup
from ..utils.helpers import get_user_lang
from ..utils.api_client import make_api_request

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


# --- YETKAZIB BERISH TURI TANLOVINI ISHLAYDIGAN HANDLER ---
async def handle_delivery_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Yetkazib berish yoki Olib ketish tanlovini boshqaradi."""
    # --- BU FUNKSIYANING BOSHLANISHIGA LOG QO'SHISHNI UNUTMANG (DEBUG UCHUN) ---
    logger.info("handle_delivery_type_selection triggered!")
    # ----------------------------------------------------------------------
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    selection = query.data

    if selection == "checkout_set_delivery":
        logger.info(f"User {user_id} selected delivery.")
        context.user_data['checkout_delivery_type'] = 'delivery'
        keyboard = [[KeyboardButton("📍 Lokatsiya yuborish", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        message_text = "Yetkazib berish manzilini lokatsiya tugmasi orqali yuboring:" if lang_code == 'uz' else "Отправьте адрес доставки с помощью кнопки геолокации:"
        # Oldingi xabarni tahrirlaymiz
        try:
            await query.edit_message_text(text=message_text)
        except Exception as e:
            logger.warning(f"Could not edit msg for location request: {e}")
            await context.bot.send_message(chat_id=user_id, text=message_text)
        # Reply tugmasini alohida yuboramiz
        await context.bot.send_message(chat_id=user_id, text="👇", reply_markup=reply_markup)
        return ASKING_LOCATION

    elif selection == "checkout_set_pickup":
        logger.info(f"User {user_id} selected pickup.")
        context.user_data['checkout_delivery_type'] = 'pickup'
        await show_branch_selection(update, context)  # Filiallarni ko'rsatish
        return ASKING_BRANCH

    else:
        logger.warning(f"Unexpected callback data: {selection}")
        return ASKING_DELIVERY_TYPE  # Joriy holatda qolamiz


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

    processing_text = "Buyurtma rasmiylashtirilmoqda..." if lang_code == 'uz' else "Обработка заказа..."
    if message_to_edit_id:
        try:
            await context.bot.edit_message_text(text=processing_text, chat_id=chat_id, message_id=message_to_edit_id)
        except Exception as e:
            logger.warning(f"Could not edit 'processing' msg: {e}")  # Ignore edit error
    elif message:
        await message.reply_text(processing_text)  # Send new if from text message
    else:  # Should have either query or message
        await context.bot.send_message(chat_id=chat_id, text=processing_text)

    # --- Checkout ma'lumotlarini SHARTLI RAVISHDA yig'amiz ---
    delivery_type = context.user_data.get("checkout_delivery_type")
    payment_type = context.user_data.get("checkout_payment_type")
    notes = context.user_data.get("checkout_notes", "")

    # Umumiy kerakli ma'lumotlar mavjudligini tekshiramiz
    if not delivery_type or not payment_type:
        logger.error(f"Missing critical checkout data (type or payment) for user {user_id}")
        error_text = "Xatolik: Buyurtma ma'lumotlari to'liq emas. /start bosing."  # ...
        await context.bot.send_message(chat_id=chat_id, text=error_text)
        # Kontekstni tozalash
        keys_to_clear = ['checkout_delivery_type', 'checkout_pickup_branch_id', 'checkout_latitude',
                         'checkout_longitude', 'checkout_payment_type', 'checkout_notes', 'checkout_address']
        for key in keys_to_clear:
            if key in context.user_data: del context.user_data[key]
        return ConversationHandler.END

    # API uchun payloadni boshlang'ich holatga keltiramiz
    checkout_data = {
        "delivery_type": delivery_type,
        "payment_type": payment_type,
        "notes": notes,
    }

    # Yetkazib berish turiga qarab qo'shimcha ma'lumotlarni qo'shamiz
    if delivery_type == 'delivery':
        latitude = context.user_data.get("checkout_latitude")
        longitude = context.user_data.get("checkout_longitude")
        address = context.user_data.get("checkout_address")  # Optional
        if latitude is None or longitude is None:
            logger.error(f"Missing location for delivery checkout for user {user_id}")
            error_text = "Xatolik: Yetkazib berish uchun lokatsiya topilmadi. /start bosing."  # ...
            await context.bot.send_message(chat_id=chat_id, text=error_text)
            keys_to_clear = ['checkout_delivery_type', 'checkout_pickup_branch_id', 'checkout_latitude',
                             'checkout_longitude', 'checkout_payment_type', 'checkout_notes', 'checkout_address']
            for key in keys_to_clear:
                if key in context.user_data: del context.user_data[key]
            return ConversationHandler.END
        checkout_data['latitude'] = latitude
        checkout_data['longitude'] = longitude
        if address: checkout_data['address'] = address  # Faqat mavjud bo'lsa qo'shamiz
    elif delivery_type == 'pickup':
        branch_id = context.user_data.get("checkout_pickup_branch_id")
        if not branch_id:
            logger.error(f"Missing branch_id for pickup checkout for user {user_id}")
            error_text = "Xatolik: Olib ketish uchun filial topilmadi. /start bosing."  # ...
            await context.bot.send_message(chat_id=chat_id, text=error_text)
            keys_to_clear = ['checkout_delivery_type', 'checkout_pickup_branch_id', 'checkout_latitude',
                             'checkout_longitude', 'checkout_payment_type', 'checkout_notes', 'checkout_address']
            for key in keys_to_clear:
                if key in context.user_data: del context.user_data[key]
            return ConversationHandler.END
        checkout_data['pickup_branch_id'] = branch_id
    # ---------------------------------------------------------

    logger.info(f"Final checkout data for user {user_id}: {checkout_data}")

    # API ga so'rov yuboramiz
    api_response = await make_api_request(context, 'POST', 'orders/checkout/', user_id, data=checkout_data)

    final_message = ""
    final_markup = get_main_menu_markup(context)

    if api_response and api_response.get('status_code') == 201 and not api_response.get('error'):
        # ... (Muvaffaqiyatli javobni formatlash - avvalgidek) ...
        order_id = api_response.get('id')
        # ... (qolgan qismi #195 da) ...
        final_message = f"✅ Buyurtmangiz <b>#{order_id}</b> muvaffaqiyatli rasmiylashtirildi!\n"  # ... (vaqtlar bilan)

    else:  # API Xatoligi
        # ... (API xatoligini formatlash - avvalgidek) ...
        error_detail = api_response.get('detail',
                                        'Noma\'lum xatolik') if api_response else 'Server bilan bog\'lanish xatosi'
        # ... (log yozish) ...
        final_message = f"❌ Buyurtmani rasmiylashtirishda xatolik: {str(error_detail)[:100]}"  # ...

    # Yakuniy xabarni yuboramiz
    # Avvalgi processing xabarni o'chirish yaxshiroq bo'lishi mumkin
    if message_to_edit_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_to_edit_id)
        except:
            pass
    await context.bot.send_message(chat_id=chat_id, text=final_message, reply_markup=final_markup,
                                   parse_mode=ParseMode.HTML)

    # Checkout kontekstini tozalaymiz
    keys_to_clear = ['checkout_delivery_type', 'checkout_pickup_branch_id', 'checkout_latitude', 'checkout_longitude',
                     'checkout_payment_type', 'checkout_notes', 'checkout_address']
    for key in keys_to_clear:
        if key in context.user_data:
            try:
                del context.user_data[key]
            except KeyError:
                pass

    return ConversationHandler.END


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
    """Foydalanuvchi lokatsiya yuborganda ishlaydi."""
    message = update.message  # Lokatsiya xabar sifatida keladi
    location = message.location
    user = update.effective_user
    user_id = user.id
    lang_code = get_user_lang(context)

    if location:
        lat = location.latitude
        lon = location.longitude
        logger.info(f"User {user_id} sent location: Lat {lat}, Lon {lon}")

        # Lokatsiyani keyinchalik checkoutda ishlatish uchun kontekstga saqlaymiz
        context.user_data['checkout_latitude'] = lat
        context.user_data['checkout_longitude'] = lon

        # To'lov turini so'raymiz
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
            # ConversationHandler'dagi fallback ushlaydi
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Yangi xabar yuboramiz (bu ReplyKeyboardni ham olib tashlaydi)
        await message.reply_text(
            text=payment_prompt,
            reply_markup=reply_markup  # Inline tugmalar bilan
        )

        return ASKING_PAYMENT  # To'lov turini kutish holatiga o'tamiz
    else:
        # Agar lokatsiya kelmasa (filtr bo'lsa ham, ehtimoldan xoli emas)
        logger.warning(f"Location handler triggered for user {user_id} but no location found in message.")
        await message.reply_text(
            "Lokatsiya qabul qilishda xatolik. Qaytadan yuboring yoki /cancel bosing." if lang_code == 'uz' else "Ошибка при получении локации. Отправьте снова или нажмите /cancel.")
        return ASKING_LOCATION  # Shu holatda qolamiz


# --- BUYURTMALAR TARIXI VA DETALLARI UCHUN FUNKSIYALAR ---
# async def show_order_history(...): ... # Buni ham shu faylga ko'chirish mumkin
# async def show_order_detail(...): ... # Buni ham

# --- CHECKOUT JARAYONINING BOSHQICH HANDLERLARI ---
# async def handle_branch_selection(...): ...
# async def handle_location(...): ...
# async def handle_payment_selection(...): ...
# async def handle_notes(...): ...
# async def confirm_order(...): ... # Bu yerda POST /orders/checkout chaqiriladi


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

# Buyurtma detallarini ko'rsatish uchun ham funksiya yaratish mumkin
# async def show_order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, order_data: dict): ...
