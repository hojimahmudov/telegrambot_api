# bot/handlers/start_auth.py
import logging
import re
from telegram import (Update, InlineKeyboardMarkup, InlineKeyboardButton,
                      ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove)
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

# Loyihadagi boshqa modullardan importlar
from ..config import SELECTING_LANG, AUTH_CHECK, WAITING_PHONE, WAITING_OTP, MAIN_MENU, ASKING_DELIVERY_TYPE, \
    CHOOSING_PHONE_METHOD, WAITING_MANUAL_PHONE
from ..keyboards import get_language_keyboard, get_registration_keyboard, get_phone_keyboard, get_main_menu_markup
from ..utils.helpers import get_user_lang, get_user_token_data, store_user_token_data, clear_user_token_data, \
    save_user_language_preference
from ..utils.api_client import make_api_request, update_language_in_db_api

logger = logging.getLogger(__name__)


# /start buyrug'i
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Bot ishga tushganda yoki tilni o'zgartirish kerak bo'lganda birinchi ishlaydi."""
    user = update.effective_user
    user_id = user.id
    logger.info(f"User {user_id} ({user.first_name}) called /start.")

    # 1. user_data dan tilni tekshiramiz
    lang_code = context.user_data.get('language_code')

    if not lang_code:
        # 2. Agar user_data da yo'q bo'lsa, va foydalanuvchi tizimga kirgan bo'lsa, profildan olamiz
        token_data = await get_user_token_data(context, user_id)
        if token_data:
            logger.info(f"User {user_id} has token, attempting to fetch profile for language.")
            profile_data = await make_api_request(context, 'GET', 'users/profile/', user_id)
            if profile_data and not profile_data.get('error'):
                db_lang = profile_data.get('language_code')
                if db_lang:
                    logger.info(f"Found language '{db_lang}' in profile for user {user_id}.")
                    context.user_data['language_code'] = db_lang
                    lang_code = db_lang

    if lang_code:
        # Agar til ma'lum bo'lsa, to'g'ridan-to'g'ri keyingi bosqichga o'tamiz
        logger.info(f"User {user_id} already has language '{lang_code}'. Proceeding to auth check.")
        # `update` callback_query emas, message bo'lishi mumkin. `check_auth_and_proceed` buni hisobga olishi kerak.
        return await check_auth_and_proceed(update, context)  # update obyektini to'g'ri uzatamiz
    else:
        # Agar til hali ham noma'lum bo'lsa, so'raymiz
        logger.info(f"Language not set for user {user_id}. Asking for language selection.")
        reply_markup = get_language_keyboard()
        await update.message.reply_text(
            "Iltimos, muloqot tilini tanlang / Пожалуйста, выберите язык общения:",
            reply_markup=reply_markup
        )
        return SELECTING_LANG


# Til tanlash callback'i
async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    lang_code = query.data.split('_')[-1]
    context.user_data['language_code'] = lang_code  # Joriy sessiyaga saqlaymiz
    logger.info(f"User {user_id} selected language: {lang_code} (in session)")

    # Agar foydalanuvchi allaqachon tizimga kirgan bo'lsa, DBdagi tilini ham yangilaymiz
    token_data = await get_user_token_data(context, user_id)  # Bu botning DB sidan oladi
    if token_data:
        logger.info(f"User {user_id} is authenticated. Updating language preference in API and bot's DB.")
        # 1. Backend API da yangilaymiz
        api_updated_successfully = await update_language_in_db_api(context, user_id, lang_code)
        if api_updated_successfully:
            # 2. Agar API da muvaffaqiyatli bo'lsa, botning o'zining DB sida ham yangilaymiz
            await save_user_language_preference(user_id, lang_code)
            logger.info(
                f"Language preference '{lang_code}' saved to bot's DB for user {user_id} after API confirmation.")
        else:
            logger.warning(
                f"Failed to update language in API for user {user_id}. Bot's DB not updated with new preference '{lang_code}'.")
            # Foydalanuvchiga xatolik haqida aytish mumkin, lekin sessiyadagi til o'zgargan
    else:
        # Agar foydalanuvchi hali login qilmagan bo'lsa, til faqat user_data da saqlanadi.
        # Login qilgandan keyin (otp_handler da) DB ga yoziladi.
        logger.info(
            f"User {user_id} is not authenticated. Language '{lang_code}' set in session only (will be saved to DB after login).")

    confirmation_text = "Til tanlandi!" if lang_code == 'uz' else "Язык выбран!"
    try:
        await query.edit_message_text(text=confirmation_text)
    except Exception as e:
        logger.warning(f"Could not edit language selection message: {e}")
        await context.bot.send_message(chat_id=user_id, text=confirmation_text)

    return await check_auth_and_proceed(update, context)


# Autentifikatsiyani tekshirish va davom etish
async def check_auth_and_proceed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    user = update.effective_user
    user_id = user.id
    lang_code = get_user_lang(context)
    token_data = await get_user_token_data(context, user_id)
    is_authenticated = False

    if token_data:
        logger.info(f"Checking token validity for user {user_id}")
        profile_data = await make_api_request(context, 'GET', 'users/profile/', user_id)
        if profile_data and not profile_data.get('error'):
            is_authenticated = True
            logger.info(f"User {user_id} is authenticated.")
            db_lang = profile_data.get('language_code')
            if db_lang and db_lang != lang_code:
                context.user_data['language_code'] = db_lang
                logger.info(f"User {user_id} language updated from DB: {db_lang}")
                lang_code = db_lang
        elif profile_data and profile_data.get('status_code') in [401, 403]:
            logger.info(f"Token invalid/expired for {user_id}, handled by make_api_request")
        elif profile_data and profile_data.get('error'):
            error_text = "Profilni tekshirishda xatolik." if lang_code == 'uz' else "Ошибка при проверке профиля."
            # Bu yerda xabar yuborish o'rniga, balki state'ni AUTH_CHECK ga o'tkazish kerakdir?
            # Hozircha xabar yuboramiz va suhbatni tugatamiz
            chat_id_to_send = update.effective_chat.id
            await context.bot.send_message(chat_id=chat_id_to_send, text=error_text)
            return ConversationHandler.END

    if is_authenticated:
        welcome_text = "Asosiy menyu." if lang_code == 'uz' else "Главное меню."
        main_markup = get_main_menu_markup(context)
        chat_id_to_send = update.effective_chat.id
        await context.bot.send_message(chat_id=chat_id_to_send, text=welcome_text, reply_markup=main_markup)
        return MAIN_MENU
    else:
        reply_markup = get_registration_keyboard(lang_code)
        prompt_text = "Davom etish uchun tizimga kirishingiz yoki ro'yxatdan o'tishingiz kerak." if lang_code == 'uz' else "Для продолжения необходимо войти или зарегистрироваться."
        # Til tanlash xabarini tahrirlash yoki yangi yuborish
        if update.callback_query:
            try:
                await update.callback_query.edit_message_text(text=prompt_text, reply_markup=reply_markup)
            except Exception as e:  # Agar tahrirlab bo'lmasa
                logger.warning(f"Could not edit message for auth prompt: {e}")
                await context.bot.send_message(chat_id=user_id, text=prompt_text, reply_markup=reply_markup)
        else:  # Agar /start dan kelgan bo'lsa
            await update.message.reply_text(text=prompt_text, reply_markup=reply_markup)
        return AUTH_CHECK  # Ro'yxatdan o'tish tugmasini kutish holati


# "Ro'yxatdan o'tish" tugmasi callback'i
async def start_registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """ "Ro'yxatdan o'tish / Kirish" tugmasi bosilganda, telefon raqamini kiritish usulini so'raydi."""
    query = update.callback_query
    await query.answer()
    lang_code = get_user_lang(context)
    user_id = query.from_user.id
    logger.info(f"User {user_id} initiated registration, asking for phone input method.")

    share_contact_text = "📱 Kontaktni ulashish" if lang_code == 'uz' else "📱 Поделиться контактом"
    manual_input_text = "✍️ Raqamni qo'lda kiritish" if lang_code == 'uz' else "✍️ Ввести номер вручную"
    cancel_text = "❌ Bekor qilish" if lang_code == 'uz' else "❌ Отмена"

    keyboard = [
        [InlineKeyboardButton(share_contact_text, callback_data='reg_share_contact')],
        [InlineKeyboardButton(manual_input_text, callback_data='reg_enter_phone')],
        [InlineKeyboardButton(cancel_text, callback_data='cancel_registration')]
        # Bu cancel uchun alohida handler kerak bo'ladi
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "Telefon raqamingizni qanday kiritmoqchisiz?" if lang_code == 'uz' else "Как вы хотите ввести свой номер телефона?"

    try:
        await query.edit_message_text(text=message_text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"Could not edit registration start message: {e}")
        await context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup)

    return CHOOSING_PHONE_METHOD


async def choose_phone_method_share_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """ "Kontaktni ulashish" tugmasi bosilganda."""
    query = update.callback_query
    await query.answer()
    lang_code = get_user_lang(context)
    user_id = query.from_user.id

    reply_markup = get_phone_keyboard(lang_code)  # Kontakt so'rash klaviaturasini olamiz
    message_text = "Iltimos, quyidagi tugma orqali Telegramga ulangan telefon raqamingizni yuboring:" if lang_code == 'uz' else "Пожалуйста, отправьте свой номер телефона, привязанный к Telegram, с помощью кнопки ниже:"

    try:
        await query.edit_message_text(text=message_text)
    except Exception as e:
        logger.warning(f"Could not edit share contact prompt: {e}")
        await context.bot.send_message(chat_id=user_id, text=message_text)

    # ReplyKeyboard'ni chiqarish uchun yordamchi xabar
    await context.bot.send_message(chat_id=user_id, text="👇", reply_markup=reply_markup)
    return WAITING_PHONE


async def choose_phone_method_manual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """ "Raqamni qo'lda kiritish" tugmasi bosilganda."""
    query = update.callback_query
    await query.answer()
    lang_code = get_user_lang(context)
    user_id = query.from_user.id

    message_text = "Iltimos, telefon raqamingizni xalqaro formatda kiriting (masalan, +998901234567):" if lang_code == 'uz' else "Пожалуйста, введите свой номер телефона в международном формате (например, +998901234567):"

    try:
        await query.edit_message_text(text=message_text, reply_markup=None)  # Tugmalarni olib tashlaymiz
    except Exception as e:
        logger.warning(f"Could not edit manual phone input prompt: {e}")
        await context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=None)

    return WAITING_MANUAL_PHONE


async def manual_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Foydalanuvchi qo'lda kiritgan telefon raqamini qabul qiladi."""
    user = update.effective_user
    phone_number_input = update.message.text
    telegram_id = user.id
    first_name = user.first_name
    last_name = user.last_name
    lang_code = get_user_lang(context)

    # Telefon raqami formatini tekshiramiz (masalan, +998 bilan boshlanishi va 13 ta belgi)
    # Bu validatsiya backenddagiga o'xshash bo'lishi kerak
    phone_regex = r'^\+998\d{9}$'
    if not re.match(phone_regex, phone_number_input):
        error_text = "Telefon raqami noto'g'ri formatda kiritildi. Iltimos, +998XXXXXXXXX formatida qayta kiriting yoki /cancel bosing." if lang_code == 'uz' else "Номер телефона введен в неверном формате. Пожалуйста, введите снова в формате +998XXXXXXXXX или нажмите /cancel."
        await update.message.reply_text(error_text)
        return WAITING_MANUAL_PHONE  # Shu holatda qolamiz

    logger.info(f"Received manually entered phone from {telegram_id}: {phone_number_input}")
    context.user_data['registration_phone_number'] = phone_number_input  # Saqlaymiz

    registration_data = {
        "telegram_id": telegram_id,
        "phone_number": phone_number_input,
        "first_name": first_name,
        "last_name": last_name or "",
        "username": user.username
    }
    api_response = await make_api_request(context, 'POST', 'auth/register/', telegram_id, data=registration_data)

    if api_response and not api_response.get('error'):
        message_text = "Rahmat! Tasdiqlash kodi Telegram orqali sizga yuborildi. Iltimos, kodni shu yerga kiriting:" if lang_code == 'uz' else "Спасибо! Код подтверждения отправлен вам в Telegram. Пожалуйста, введите код здесь:"
        await update.message.reply_text(message_text, reply_markup=ReplyKeyboardRemove())
        return WAITING_OTP
    else:
        # ... (contact_handler'dagi kabi xatolikni qayta ishlash) ...
        error_detail = api_response.get('detail', 'Noma\'lum xatolik') if api_response else 'Server bilan xatolik'
        logger.warning(f"Manual Phone Registration API error for {telegram_id}: {error_detail}")
        error_text = f"Xatolik: {error_detail}. /start bosing." if lang_code == 'uz' else f"Ошибка: {error_detail}. Нажмите /start."
        await update.message.reply_text(error_text, reply_markup=ReplyKeyboardRemove())
        if 'registration_phone_number' in context.user_data: del context.user_data['registration_phone_number']
        return ConversationHandler.END


# Kontakt handler
async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    contact = update.message.contact
    user = update.effective_user
    phone_number = contact.phone_number
    telegram_id = user.id
    first_name = user.first_name
    last_name = user.last_name
    telegram_username = user.username
    lang_code = get_user_lang(context)
    if not phone_number.startswith('+'): phone_number = '+' + phone_number
    logger.info(f"Received contact from {telegram_id}: {phone_number}")
    context.user_data['registration_phone_number'] = phone_number
    registration_data = {
        "telegram_id": telegram_id, "phone_number": phone_number,
        "first_name": first_name, "last_name": last_name or "",
        "username": telegram_username
    }
    api_response = await make_api_request(context, 'POST', 'auth/register/', telegram_id, data=registration_data)
    if api_response and not api_response.get('error'):
        message_text = "Rahmat! Tasdiqlash kodi Telegram orqali sizga yuborildi. Iltimos, kodni shu yerga kiriting:" if lang_code == 'uz' else "Спасибо! Код подтверждения отправлен вам в Telegram. Пожалуйста, введите код здесь:"
        await update.message.reply_text(message_text, reply_markup=ReplyKeyboardRemove())
        return WAITING_OTP
    else:
        error_detail = api_response.get('detail',
                                        'Noma\'lum server xatoligi') if api_response else 'Server bilan bog\'lanish xatosi'
        status_code = api_response.get('status_code', 500) if api_response else 500
        logger.warning(f"Registration API error for {telegram_id}: Status {status_code} - {error_detail}")
        if "allaqachon aktiv" in str(error_detail).lower():
            error_text = "Bu raqam allaqachon ro'yxatdan o'tgan va aktiv." if lang_code == 'uz' else "Этот номер уже зарегистрирован и активен."
        elif "boshqa foydalanuvchi" in str(error_detail).lower():
            error_text = "Xatolik: Telegram ID yoki telefon raqami boshqa foydalanuvchiga tegishli." if lang_code == 'uz' else "Ошибка: Telegram ID или номер телефона принадлежат другому пользователю."
        else:
            error_text = f"Xatolik yuz berdi ({str(error_detail)[:50]}...). /start bosing." if lang_code == 'uz' else f"Произошла ошибка ({str(error_detail)[:50]}...). Нажмите /start."
        await update.message.reply_text(error_text, reply_markup=ReplyKeyboardRemove())
        if 'registration_phone_number' in context.user_data: del context.user_data['registration_phone_number']
        return ConversationHandler.END


# OTP handler
async def otp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    user = update.effective_user
    user_id = user.id
    otp_code = update.message.text
    # Tilni joriy sessiyadagi user_data dan olamiz
    lang_code = context.user_data.get('language_code', 'uz')

    if not re.match(r'^\d{4,6}$', otp_code):
        # ... (xato matni va WAITING_OTP qaytarish) ...
        error_text = "Noto'g'ri formatdagi kod. Iltimos, 4-6 xonali raqam kiriting." if lang_code == 'uz' else "Неверный формат кода. Пожалуйста, введите 4-6 значный код."
        await update.message.reply_text(error_text)
        return WAITING_OTP

    phone_number = context.user_data.get('registration_phone_number')
    if not phone_number:
        # ... (xato matni va ConversationHandler.END qaytarish) ...
        logger.error(f"OTP: Phone number not found in user_data for user {user_id}.")
        error_text = "Ichki xatolik (telefon raqam). /start." if lang_code == 'uz' else "Внутренняя ошибка (номер телефона). /start."
        await update.message.reply_text(error_text)
        return ConversationHandler.END

    logger.info(f"OTP: Received OTP {otp_code} for phone {phone_number} from user {user_id}")

    verification_data = {"phone_number": phone_number, "otp_code": otp_code}
    api_response = await make_api_request(context, 'POST', 'auth/verify/', user_id, data=verification_data)

    if api_response and not api_response.get('error'):
        access_token = api_response.get('access_token')
        refresh_token = api_response.get('refresh_token')
        user_api_data = api_response.get('user')  # API dan kelgan user ma'lumotlari

        if access_token and refresh_token and user_api_data:
            # store_user_token_data endi DBga yozadi (joriy sessiyadagi til bilan birga)
            await store_user_token_data(context, user_id, access_token, refresh_token)

            # Backenddagi profil tilini ham sessiyadagi tilga moslaymiz
            # (agar register paytida backend default tilni o'rnatgan bo'lsa yoki user boshqa tilda kirsa)
            backend_lang = user_api_data.get('language_code')
            if lang_code != backend_lang:  # Agar sessiyadagi til backendnikidan farq qilsa
                logger.info(f"OTP: Syncing session language '{lang_code}' to backend profile for user {user_id}")
                api_lang_updated = await update_language_in_db_api(context, user_id, lang_code)
                if api_lang_updated:
                    logger.info(
                        f"OTP: Language '{lang_code}' synced to backend API profile for user {user_id} after login.")
                else:
                    logger.warning(
                        f"OTP: Failed to sync language '{lang_code}' to backend API profile for user {user_id} after login.")
            else:
                logger.info(f"OTP: Language '{lang_code}' already matches backend profile for user {user_id}.")

            success_text = "Muvaffaqiyatli! Siz tizimga kirdingiz." if lang_code == 'uz' else "Успешно! Вы вошли в систему."
            await update.message.reply_text(success_text, reply_markup=get_main_menu_markup(context))

            if 'registration_phone_number' in context.user_data:
                del context.user_data['registration_phone_number']
            return MAIN_MENU
        else:
            # ... (API dan noto'g'ri javob) ...
            logger.error(f"OTP: Invalid response structure from /auth/verify/ for user {user_id}: {api_response}")
            error_text = "Tizimdan javob olishda xatolik." if lang_code == 'uz' else "Ошибка при получении ответа от системы."
            await update.message.reply_text(error_text)
            return WAITING_OTP
    else:
        # ... (API xatoligi: noto'g'ri kod va h.k.) ...
        error_detail = api_response.get('detail',
                                        'Noma\'lum xatolik') if api_response else 'Server bilan bog\'lanish xatosi'
        logger.warning(f"OTP Verification API error for user {user_id}: {error_detail}")
        if "Noto'g'ri yoki muddati o'tgan" in str(error_detail):
            error_text = "Kiritilgan kod noto'g'ri yoki muddati o'tgan. Qaytadan kiriting yoki /cancel." if lang_code == 'uz' else "Введенный код неверный или истек. Введите снова или /cancel."
        else:
            error_text = f"Xatolik: {str(error_detail)[:100]}" if lang_code == 'uz' else f"Ошибка: {str(error_detail)[:100]}"
        await update.message.reply_text(error_text)
        return WAITING_OTP
