# bot/handlers/start_auth.py
import logging
import re
from telegram import (Update, InlineKeyboardMarkup, InlineKeyboardButton,
                      ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove)
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

# Loyihadagi boshqa modullardan importlar
from ..config import SELECTING_LANG, AUTH_CHECK, WAITING_PHONE, MAIN_MENU, ASKING_DELIVERY_TYPE, \
    CHOOSING_PHONE_METHOD, WAITING_MANUAL_PHONE
from ..keyboards import get_language_keyboard, get_registration_keyboard, get_phone_keyboard, get_main_menu_markup
from ..utils.db_utils import get_user_session_data
from ..utils.helpers import get_user_lang, get_user_token_data, store_user_token_data, clear_user_token_data, \
    save_user_language_preference
from ..utils.api_client import make_api_request, update_language_in_db_api

logger = logging.getLogger(__name__)


# /start buyrug'i
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    user = update.effective_user
    user_id = user.id
    logger.info(f"User {user_id} ({user.first_name}) called /start.")

    lang_code = context.user_data.get('language_code')

    if not lang_code:
        logger.info(f"Language not in session for user {user_id}. Checking bot's DB.")
        session_data_from_db = get_user_session_data(user_id)  # Bu sinxron SQLite chaqiruvi
        if session_data_from_db and session_data_from_db.get('lang'):
            lang_code = session_data_from_db['lang']
            context.user_data['language_code'] = lang_code
            logger.info(f"User {user_id} language '{lang_code}' loaded from bot's DB into session.")

    if lang_code:
        logger.info(f"User {user_id} proceeding with language '{lang_code}'.")
        return await check_auth_and_proceed(update, context)
    else:
        logger.info(f"Language still not set for user {user_id}. Asking for language selection.")
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
    user = update.effective_user  # Endi bu yerda effective_user bor
    user_id = user.id
    # get_user_lang endi faqat context.user_data dan oladi.
    # Agar user_data.language_code bo'lmasa (masalan, /start dan keyin DB dan ham topilmasa), 'uz' bo'ladi.
    lang_code = get_user_lang(context)

    token_data = await get_user_token_data(context, user_id)  # DB dan oladi
    is_authenticated = False

    if token_data:
        logger.info(f"User {user_id} has token from bot's DB. Checking API profile with lang: {lang_code}")
        profile_data = await make_api_request(context, 'GET', 'users/profile/',
                                              user_id)  # make_api_request lang_code ni contextdan oladi

        if profile_data and not profile_data.get('error'):
            is_authenticated = True
            logger.info(f"User {user_id} is authenticated via API.")

            backend_lang = profile_data.get('language_code')
            # context.user_data['language_code'] endi /start da DB dan o'rnatilgan bo'lishi mumkin
            session_lang = context.user_data.get('language_code')

            if backend_lang:  # Agar backendda til bo'lsa
                if backend_lang != session_lang:
                    logger.info(
                        f"User {user_id} session lang ('{session_lang}') differs from API lang ('{backend_lang}'). Updating session & bot's DB.")
                    context.user_data['language_code'] = backend_lang
                    await save_user_language_preference(user_id, backend_lang)  # Botning SQLite siga yozamiz
                lang_code = backend_lang  # Har doim backenddagi tilni ustun ko'ramiz, agar mavjud bo'lsa
            elif session_lang:  # Backendda yo'q, lekin sessiyada bor (masalan, yangi user til tanlagan)
                logger.info(
                    f"User {user_id} has session lang '{session_lang}', API has no lang. Attempting to update API & bot's DB.")
                api_updated = await update_language_in_db_api(context, user_id, session_lang)
                if api_updated:
                    await save_user_language_preference(user_id, session_lang)  # Botning SQLite siga ham yozamiz
                lang_code = session_lang
            else:  # Hech qayerda til yo'q (bo'lmasligi kerak)
                lang_code = 'uz'  # Fallback
                context.user_data['language_code'] = lang_code
                logger.warning(f"User {user_id} - No language found in session or API. Defaulting to '{lang_code}'.")
        # Agar profile_data xatolik qaytarsa (masalan 401), make_api_request tokenni tozalaydi
        # va is_authenticated False bo'lib qoladi.

    # lang_code check_auth_and_proceed boshida context.user_data dan olinadi.
    # get_user_lang uni qaytaradi. Agar u yerda bo'lmasa, 'uz' default.
    # Yuqoridagi if blokida u API dan kelgan til bilan yangilanishi mumkin.

    if is_authenticated:
        # ... (asosiy menyuni chiqarish, MAIN_MENU qaytarish) ...
        welcome_text = "Asosiy menyu." if lang_code == 'uz' else "Главное меню."
        main_markup = get_main_menu_markup(context)  # Bu ham lang_code ni contextdan oladi
        await context.bot.send_message(chat_id=user_id, text=welcome_text, reply_markup=main_markup)
        return MAIN_MENU
    else:
        # ... (ro'yxatdan o'tish tugmasini chiqarish, AUTH_CHECK qaytarish) ...
        reply_markup = get_registration_keyboard(lang_code)
        prompt_text = "Davom etish uchun tizimga kirishingiz yoki ro'yxatdan o'tishingiz kerak." if lang_code == 'uz' else "Для продолжения необходимо войти или зарегистрироваться."
        # ... (xabar yuborish logikasi) ...
        if update.callback_query and update.callback_query.message:
            try:
                await update.callback_query.edit_message_text(text=prompt_text, reply_markup=reply_markup)
            except Exception as e:
                logger.warning(f"Could not edit for reg prompt: {e}");
                await context.bot.send_message(chat_id=user_id,
                                               text=prompt_text,
                                               reply_markup=reply_markup)
        elif update.message:
            await update.message.reply_text(text=prompt_text, reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id=user_id, text=prompt_text, reply_markup=reply_markup)
        return AUTH_CHECK


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


async def process_phone_for_login(update: Update, context: ContextTypes.DEFAULT_TYPE, phone_number: str):
    """Telefon raqamini qabul qilib, APIga yuboradi va tokenlarni oladi."""
    user = update.effective_user
    # --- USER_ID NI ANIQLAB OLAMIZ VA ISHLATAMIZ ---
    current_user_id = user.id  # Foydalanish uchun alohida o'zgaruvchiga olamiz
    # ---------------------------------------------
    lang_code = get_user_lang(context)

    login_data = {
        "telegram_id": current_user_id,  # user.id o'rniga
        "phone_number": phone_number,
        "first_name": user.first_name,
        "last_name": user.last_name or "",
        "username": user.username
    }

    # make_api_request user_id ni kutadi (bu telegram_id)
    api_response = await make_api_request(context, 'POST', 'auth/register/', current_user_id, data=login_data)

    if api_response and not api_response.get('error') and api_response.get('status_code') in [200, 201]:
        access_token = api_response.get('access_token')
        refresh_token = api_response.get('refresh_token')
        user_api_data = api_response.get('user')

        if access_token and refresh_token and user_api_data:
            # --- TO'G'RILANGAN QATOR ---
            # Endi current_user_id ni ishlatamiz
            await store_user_token_data(context, current_user_id, access_token, refresh_token)
            # -------------------------

            # Tilni sinxronlash logikasi (avvalgidek)
            backend_lang = user_api_data.get('language_code')
            # lang_code bu joriy sessiyadagi tanlangan til
            if lang_code != backend_lang and backend_lang is not None:
                logger.info(f"Login: Syncing API lang '{backend_lang}' to bot's DB for user {current_user_id}.")
                await save_user_language_preference(current_user_id, backend_lang)  # Botning SQLite siga
                context.user_data['language_code'] = backend_lang  # Sessiyaga ham
            elif lang_code and backend_lang is None:  # Agar backendda til yo'q bo'lsa, sessiyadagini yozamiz
                logger.info(
                    f"Login: Syncing session lang '{lang_code}' to API and bot's DB for user {current_user_id}.")
                api_lang_updated = await update_language_in_db_api(context, current_user_id, lang_code)
                # save_user_language_preference store_user_token_data ichida chaqiriladi
                # (chunki store_user_token_data tilni ham saqlaydi)
                # Shuning uchun bu yerda alohida save_user_language_preference shart emas,
                # chunki store_user_token_data joriy lang_code ni olib DBga yozadi.
                # Lekin API ga yozish kerak bo'lsa, update_language_in_db_api qoladi.
                if not api_lang_updated:
                    logger.warning(
                        f"Login: Failed to sync language '{lang_code}' to backend API for user {current_user_id} after login.")

            success_message = api_response.get("message", "Muvaffaqiyatli!")
            await update.message.reply_text(success_message, reply_markup=get_main_menu_markup(context))
            return MAIN_MENU
        else:
            logger.error(
                f"Login Error: Invalid token structure in API response for {current_user_id}. Resp: {api_response}")
            error_text = "Tizimga kirishda xatolik (token tuzilishi)." if lang_code == 'uz' else "Ошибка входа в систему (структура токена)."
            await update.message.reply_text(error_text, reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
    else:
        # ... (API xatoligini qayta ishlash - avvalgidek) ...
        error_detail = api_response.get('detail', api_response.get('error',
                                                                   'Noma\'lum xatolik')) if api_response else 'Server bilan bog\'lanish xatosi'
        await update.message.reply_text(f"Xatolik: {error_detail}.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    contact = update.message.contact
    phone_number = contact.phone_number
    if not phone_number.startswith('+'): phone_number = '+' + phone_number
    logger.info(f"Received contact from {update.effective_user.id}: {phone_number}")
    # context.user_data['registration_phone_number'] endi kerak emas
    return await process_phone_for_login(update, context, phone_number)


async def manual_phone_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    phone_number_input = update.message.text
    lang_code = get_user_lang(context)
    phone_regex = r'^\+998\d{9}$'
    if not re.match(phone_regex, phone_number_input):
        error_text = "Telefon raqami noto'g'ri formatda..."  # ...
        await update.message.reply_text(error_text)
        return WAITING_MANUAL_PHONE
    logger.info(f"Received manual phone from {update.effective_user.id}: {phone_number_input}")
    # context.user_data['registration_phone_number'] endi kerak emas
    return await process_phone_for_login(update, context, phone_number_input)
