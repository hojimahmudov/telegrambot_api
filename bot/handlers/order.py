# bot/handlers/order.py
import logging
import datetime  # <-- Sanani formatlash uchun (agar show_order_history'dan ko'chirsak)
from urllib.parse import urlparse, parse_qs  # <-- URL parse uchun (agar show_order_history'dan ko'chirsak)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, \
    ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

# Loyihadagi boshqa modullardan importlar
from ..config import ASKING_BRANCH, ASKING_LOCATION, MAIN_MENU, ASKING_DELIVERY_TYPE, ASKING_PAYMENT  # Kerakli holatlar
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
    logger.info("handle_delivery_type_selection triggered!")
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)
    selection = query.data  # Masalan, "checkout_set_delivery" yoki "checkout_set_pickup"

    if selection == "checkout_set_delivery":
        logger.info(f"User {user_id} selected delivery.")
        context.user_data['checkout_delivery_type'] = 'delivery'

        # Lokatsiya so'rash
        keyboard = [[KeyboardButton("📍 Lokatsiya yuborish", request_location=True)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        message_text = "Yetkazib berish manzilini lokatsiya tugmasi orqali yuboring:" if lang_code == 'uz' else "Отправьте адрес доставки с помощью кнопки геолокации:"

        # Avvalgi inline tugmalarni olib tashlab, matnni yangilaymiz
        await query.edit_message_text(text=message_text)
        # ReplyKeyboardni chiqarish uchun yordamchi xabar
        await context.bot.send_message(chat_id=user_id, text="👇", reply_markup=reply_markup)

        return ASKING_LOCATION  # Lokatsiya kutish holatiga o'tamiz

    elif selection == "checkout_set_pickup":
        logger.info(f"User {user_id} selected pickup.")
        context.user_data['checkout_delivery_type'] = 'pickup'

        # Filial tanlashni ko'rsatamiz (yuqoridagi yordamchi funksiya)
        await show_branch_selection(update, context)
        return ASKING_BRANCH  # Filial tanlashni kutish holatiga o'tamiz

    else:  # Kutilmagan callback data
        logger.warning(f"Unexpected callback data in delivery type selection: {selection}")
        return ASKING_DELIVERY_TYPE  # Joriy holatda qolamiz


async def handle_branch_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Filial tanlash tugmasi ('checkout_branch_{id}') bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    try:
        branch_id = int(query.data.split('_')[-1])
        logger.info(f"User {user_id} selected branch ID: {branch_id}")
        # Tanlangan filial ID sini kontekstga saqlaymiz
        context.user_data['checkout_pickup_branch_id'] = branch_id

        # TODO: Keyingi qadamni so'rash (masalan, to'lov turi)
        reply_text = f"Filial #{branch_id} tanlandi. Endi to'lov turini tanlang..."  # Placeholder
        await query.edit_message_text(text=reply_text)  # Hozircha tugmalarsiz
        return ASKING_PAYMENT  # To'lov turini kutish holatiga o'tamiz

    except (IndexError, ValueError, TypeError):
        logger.warning(f"Invalid branch selection callback: {query.data}")
        await query.edit_message_text("Xatolik: Filial tanlashda muammo.")
        return ASKING_BRANCH  # Shu holatda qolamiz


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Foydalanuvchi lokatsiya yuborganda ishlaydi."""
    user = update.effective_user
    user_id = user.id
    location = update.message.location
    lang_code = get_user_lang(context)
    logger.info(f"User {user_id} sent location: Lat {location.latitude}, Lon {location.longitude}")

    # Lokatsiyani kontekstga saqlaymiz
    context.user_data['checkout_latitude'] = location.latitude
    context.user_data['checkout_longitude'] = location.longitude

    # ReplyKeyboardni olib tashlaymiz va keyingi qadamni so'raymiz
    reply_text = "Lokatsiya qabul qilindi. Endi to'lov turini tanlang..."  # Placeholder
    await update.message.reply_text(text=reply_text, reply_markup=ReplyKeyboardRemove())  # Hozircha tugmalarsiz

    return ASKING_PAYMENT  # To'lov turini kutish holatiga o'tamiz


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
