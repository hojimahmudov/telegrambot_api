# bot/handlers/start_auth.py
import logging
import re
from telegram import (Update, InlineKeyboardMarkup, InlineKeyboardButton,
                      ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove)
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

# Loyihadagi boshqa modullardan importlar
from ..config import SELECTING_LANG, AUTH_CHECK, WAITING_PHONE, WAITING_OTP, MAIN_MENU, ASKING_DELIVERY_TYPE
from ..keyboards import get_language_keyboard, get_registration_keyboard, get_phone_keyboard, get_main_menu_markup
from ..utils.helpers import get_user_lang, get_user_token_data, store_user_token_data, clear_user_token_data
from ..utils.api_client import make_api_request, update_language_in_db

logger = logging.getLogger(__name__)


# /start buyrug'i
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    user = update.effective_user
    logger.info(f"User {user.id} ({user.first_name}) called /start.")
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
    context.user_data['language_code'] = lang_code
    logger.info(f"User {user_id} selected language: {lang_code}")

    confirmation_text = "Til tanlandi!" if lang_code == 'uz' else "Язык выбран!"
    try:
        await query.edit_message_text(text=confirmation_text)
    except Exception as e:
        logger.warning(f"Could not edit language selection message: {e}")
        # await context.bot.send_message(chat_id=user_id, text=confirmation_text) # Ixtiyoriy
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
    query = update.callback_query
    await query.answer()
    lang_code = get_user_lang(context)
    user_id = query.from_user.id
    logger.info(f"User {user_id} initiated registration.")
    reply_markup = get_phone_keyboard(lang_code)
    message_text = "Iltimos, quyidagi tugma orqali Telegramga ulangan telefon raqamingizni yuboring:" if lang_code == 'uz' else "Пожалуйста, отправьте свой номер телефона, привязанный к Telegram, с помощью кнопки ниже:"
    try:
        await query.edit_message_text(text=message_text)
    except Exception as e:
        logger.warning(f"Could not edit registration start message: {e}")
        await context.bot.send_message(chat_id=user_id, text=message_text)
    await query.message.reply_text(text="👇", reply_markup=reply_markup)
    return WAITING_PHONE


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
    lang_code = get_user_lang(context)
    if not re.match(r'^\d{4,6}$', otp_code):
        error_text = "Noto'g'ri formatdagi kod..."  # Qisqa
        await update.message.reply_text(error_text)
        return WAITING_OTP
    phone_number = context.user_data.get('registration_phone_number')
    if not phone_number:
        logger.error(f"Cannot verify OTP for user {user_id}: phone number not found.")
        error_text = "Xatolik (raqam topilmadi)... /start bosing."  # Qisqa
        await update.message.reply_text(error_text)
        return ConversationHandler.END
    logger.info(f"Received OTP {otp_code} for phone {phone_number} from user {user_id}")
    verification_data = {"phone_number": phone_number, "otp_code": otp_code}
    api_response = await make_api_request(context, 'POST', 'auth/verify/', user_id, data=verification_data)
    if api_response and not api_response.get('error'):
        access_token = api_response.get('access_token')
        refresh_token = api_response.get('refresh_token')
        if access_token and refresh_token:
            await store_user_token_data(context, user_id, access_token, refresh_token)
            lang_to_save = context.user_data.get('language_code')
            if lang_to_save: await update_language_in_db(context, user_id, lang_to_save)
            success_text = "Muvaffaqiyatli! Siz tizimga kirdingiz." if lang_code == 'uz' else "Успешно! Вы вошли в систему."
            await update.message.reply_text(success_text, reply_markup=get_main_menu_markup(context))
            if 'registration_phone_number' in context.user_data: del context.user_data['registration_phone_number']
            return MAIN_MENU
        else:
            logger.error(f"Invalid response structure from /auth/verify/: {api_response}")
            error_text = "API dan noto'g'ri javob."  # Qisqa
            await update.message.reply_text(error_text)
            return WAITING_OTP
    else:
        error_detail = api_response.get('detail', 'Noma\'lum xatolik') if api_response else 'Server xatosi'
        status_code = api_response.get('status_code', 500) if api_response else 500
        logger.warning(f"OTP Verification API error for {user_id}: Status {status_code} - {error_detail}")
        if "Noto'g'ri yoki muddati o'tgan" in str(error_detail):
            error_text = "Kod xato yoki muddati o'tgan. Qayta kiriting yoki /cancel."  # Qisqa
        else:
            error_text = f"Xatolik: {str(error_detail)[:100]}"
        await update.message.reply_text(error_text)
        return WAITING_OTP
