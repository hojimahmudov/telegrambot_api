#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import httpx  # API chaqiruvlari uchun
import json
import re

# .env faylidan o'qish uchun (agar o'rnatilgan bo'lsa)
from dotenv import load_dotenv

load_dotenv()  # Skript boshida chaqirilishi kerak

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler,
    filters, CallbackQueryHandler, ConversationHandler, PicklePersistence  # Persistence qo'shildi
)
from telegram.constants import ParseMode

# --- Sozlamalar ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    # Ishlab chiqishda tokenni shu yerga qo'yish mumkin, lekin production uchun environment'dan olish shart!
    # BOT_TOKEN = "YOUR_BOT_TOKEN_HERE" # VAQTINCHALIK ISHLATISH UCHUN
    raise ValueError("Iltimos, TELEGRAM_BOT_TOKEN environment o'zgaruvchisini o'rnating.")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api/v1/")

# Logging sozlamalari
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Holatlar (States) ---
# Suhbat bosqichlarini aniqlash uchun konstantalar
SELECTING_LANG, AUTH_CHECK, WAITING_PHONE, WAITING_OTP, MAIN_MENU = map(chr, range(5))

# --- Tokenlarni Saqlash (Placeholder - XAVFSIZ EMAS!) ---
# Production uchun buni DB yoki boshqa xavfsiz joyga o'tkazing!
# PicklePersistence ishlatilsa, context.user_data da saqlanadi.

# --- API Client ---
# Bitta klient obyektini qayta ishlatamiz
api_client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=20.0)

main_menu_keyboard_uz = [
    ["🍽️ Menyu", "🛒 Savat"],
    ["📋 Buyurtmalarim", "📍 Filiallar"],
    ["👤 Profil", "⚙️ Sozlamalar"]
]
main_menu_keyboard_ru = [
    ["🍽️ Меню", "🛒 Корзина"],
    ["📋 Мои заказы", "📍 Филиалы"],
    ["👤 Профиль", "⚙️ Настройки"]
]

main_menu_markup_uz = ReplyKeyboardMarkup(main_menu_keyboard_uz, resize_keyboard=True)
main_menu_markup_ru = ReplyKeyboardMarkup(main_menu_keyboard_ru, resize_keyboard=True)


# --- Helper Functions ---
def get_user_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Foydalanuvchi kontekstidan til kodini oladi yoki standart 'uz' qaytaradi."""
    return context.user_data.get('language_code', 'uz')  # Agar persistence bo'lsa, saqlanib qoladi


def get_main_menu_markup(context: ContextTypes.DEFAULT_TYPE) -> ReplyKeyboardMarkup:
    """Foydalanuvchi tiliga mos asosiy menyu klaviaturasini qaytaradi."""
    lang_code = get_user_lang(context)  # Tilni kontekstdan olamiz
    if lang_code == 'ru':
        return main_menu_markup_ru
    else:
        # Agar til 'ru' bo'lmasa yoki aniqlanmasa, 'uz' ni qaytaramiz
        return main_menu_markup_uz


async def get_user_token_data(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> dict | None:
    """Kontekstdan (yoki persistent storage'dan) foydalanuvchi tokenini oladi."""
    # Persistence ishlatilsa, user_data da bo'ladi
    return context.user_data.get('tokens')


async def store_user_token_data(context: ContextTypes.DEFAULT_TYPE, user_id: int, access: str, refresh: str):
    """Tokenlarni kontekstga (va persistence orqali) saqlaydi."""
    context.user_data['tokens'] = {'access': access, 'refresh': refresh}
    logger.info(f"Tokens stored in context for user {user_id}")
    # Persistence ishlatilsa, avtomatik saqlanadi


async def clear_user_token_data(context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Tokenlarni kontekstdan (va persistence'dan) o'chiradi."""
    if 'tokens' in context.user_data:
        del context.user_data['tokens']
        logger.info(f"Tokens cleared from context for user {user_id}")


async def make_api_request(context: ContextTypes.DEFAULT_TYPE, method: str, endpoint: str, user_id: int,
                           data: dict = None, params: dict = None) -> dict | None:
    """
    API ga autentifikatsiya va til sarlavhasi bilan so'rov yuborish uchun yordamchi funksiya.
    Muvaffaqiyatli bo'lsa dict ko'rinishidagi JSON javobni qaytaradi.
    Xatolik bo'lsa, 'error' kaliti bilan dict qaytaradi.
    Kritik token xatoligida None qaytarishi mumkin (qayta login uchun).
    """
    token_data = await get_user_token_data(context, user_id)  # Tokenni olish funksiyasini chaqiramiz
    lang_code = get_user_lang(context)  # Tilni olish funksiyasini chaqiramiz
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Language": lang_code
    }
    if token_data and token_data.get('access'):
        headers["Authorization"] = f"Bearer {token_data['access']}"
        # logger.debug(f"Using token for user {user_id} for request to {endpoint}")
    # else:
    # logger.debug(f"No token found or used for user {user_id} for request to {endpoint}")

    try:
        logger.debug(
            f"API Request -> {method} {endpoint} Headers: {list(headers.keys())} Data: {data} Params: {params}")
        # api_client global yoki class atributi sifatida mavjud deb hisoblaymiz
        response = await api_client.request(method, endpoint, headers=headers, json=data, params=params)
        logger.debug(f"API Response Status <- {method} {endpoint}: {response.status_code}")

        # 204 No Content kabi holatlarni tekshirish
        if response.status_code == 204:
            return {"success": True, "status_code": response.status_code}

        # Javobni JSON sifatida olishga harakat qilish
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            # Agar JSON bo'lmasa lekin status kod OK bo'lsa (masalan, 200)
            if 200 <= response.status_code < 300:
                logger.warning(
                    f"API request to {endpoint} succeeded ({response.status_code}) but returned non-JSON body.")
                return {"success": True, "status_code": response.status_code, "detail": response.text}
            else:
                # Agar xatolik statusi va JSON bo'lmasa, HTTP xatolikni ko'taramiz
                response.raise_for_status()
                return {"error": "Invalid Response Format", "detail": response.text,
                        "status_code": response.status_code}

        # Agar status kod xato bo'lsa (4xx, 5xx), exception ko'tarish
        response.raise_for_status()

        # Muvaffaqiyatli javob (2xx) va JSON mavjud
        response_data['status_code'] = response.status_code  # Status kodni ham qo'shib qo'yamiz
        return response_data

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        error_text = e.response.text
        logger.error(f"API HTTP Error for {user_id} at {endpoint}: {status_code} - {error_text}")
        try:
            error_data = e.response.json()  # API xatolikni JSONda berishi mumkin
        except json.JSONDecodeError:
            error_data = {"detail": error_text}  # Agar JSON bo'lmasa

        if status_code == 401 and token_data:  # Agar token bilan 401 xatolik kelsa
            logger.info(f"Access token expired or invalid for user {user_id}. Clearing token.")
            await clear_user_token_data(context, user_id)  # Tokkeni tozalaymiz
            # TODO: Refresh token logikasini shu yerga qo'shish mumkin
            error_message = "Sessiya muddati tugadi yoki xato token. Iltimos, /start bosing." if lang_code == 'uz' else "Сессия истекла или неверный токен. Пожалуйста, нажмите /start."
            # Bu yordamchi funksiyadan to'g'ridan-to'g'ri xabar yubormaslik yaxshiroq
            # Qaytargan xatolikni yuqori funksiya o'zi hal qiladi
            return {"error": "Unauthorized", "detail": error_message, "status_code": status_code}

        # Boshqa 4xx, 5xx xatoliklar uchun API javobini qaytaramiz
        return {"error": f"API Error {status_code}",
                "detail": error_data.get('detail', error_data.get('error', error_text)), "status_code": status_code}

    except httpx.Timeout:
        logger.error(f"{user_id} uchun {endpoint} ga so'rovda Timeout xatoligi.")
        return {"error": "Timeout", "detail": "API javob bermadi.", "status_code": 504}
    except httpx.RequestError as e:
        logger.error(f"{user_id} uchun {endpoint} ga so'rovda network xatoligi: {e}", exc_info=True)
        return {"error": "Network Error", "detail": "Server bilan bog'lanib bo'lmadi.", "status_code": 503}
    except Exception as e:
        logger.error(f"{user_id} uchun {endpoint} ga so'rovda noma'lum xatolik: {e}", exc_info=True)
        return {"error": "Unexpected Error", "detail": str(e), "status_code": 500}


async def update_language_in_db(context: ContextTypes.DEFAULT_TYPE, user_id: int, lang_code: str):
    """
    Yordamchi funksiya: Foydalanuvchi tanlagan tilni backenddagi
    profiliga PATCH so'rovi orqali saqlaydi.
    """
    # Bu funksiya make_api_request global mavjud deb hisoblaydi
    # Bu funksiya chaqirilgan paytda foydalanuvchi autentifikatsiyadan o'tgan
    # va tokeni saqlangan deb hisoblanadi.
    logger.info(f"Attempting to update language to '{lang_code}' in DB for user {user_id}")
    profile_update_data = {"language_code": lang_code}

    # make_api_request avtomatik 'Authorization' sarlavhasini qo'shadi
    api_response = await make_api_request(
        context,
        'PATCH',  # Qisman yangilash uchun PATCH
        'users/profile/',  # Profilni yangilash endpoint'i
        user_id,  # Foydalanuvchi ID si
        data=profile_update_data  # Yuboriladigan ma'lumot
    )

    if api_response and not api_response.get('error'):
        # Agar API dan xatolik qaytmasa (masalan, 200 OK)
        logger.info(f"Successfully updated language preference in DB for user {user_id}")
    else:
        # Agar tilni DB ga yozishda xatolik bo'lsa (masalan, API ishlamayapti)
        # Buni faqat logga yozamiz, bot ishlashda davom etaveradi
        logger.warning(f"Failed to update language preference in DB for user {user_id}. Response: {api_response}")


# --- /start Komandasi Uchun Handler ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Bot ishga tushganda yoki /start buyrug'i kelganda birinchi ishlaydi."""
    user = update.effective_user
    # user_data ni tozalash (ixtiyoriy, har /start da yangidan boshlash uchun)
    # context.user_data.clear()
    logger.info(f"User {user.id} ({user.first_name}) called /start.")

    # Til tanlash tugmalarini yaratamiz
    keyboard = [
        [
            InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data='set_lang_uz'),
            InlineKeyboardButton("🇷🇺 Русский", callback_data='set_lang_ru'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Til tanlashni so'raymiz
    await update.message.reply_text(
        "Iltimos, muloqot tilini tanlang / Пожалуйста, выберите язык общения:",
        reply_markup=reply_markup
    )
    return SELECTING_LANG  # Til tanlashni kutish holati


# --- Til Tanlash Uchun Callback Handler ---
async def set_language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Til tanlash tugmasi bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    lang_code = query.data.split('_')[-1]  # 'set_lang_uz' -> 'uz'
    context.user_data['language_code'] = lang_code
    logger.info(f"User {user_id} selected language: {lang_code}")

    # Tasdiq xabarini tanlangan tilda yuboramiz
    confirmation_text = "Til tanlandi!" if lang_code == 'uz' else "Язык выбран!"
    try:
        await query.edit_message_text(text=confirmation_text)
    except Exception as e:
        logger.warning(f"Could not edit language selection message: {e}")
        await context.bot.send_message(chat_id=user_id, text=confirmation_text)

    # Endi autentifikatsiyani tekshirish bosqichiga o'tamiz
    # Bu alohida funksiya bo'lishi mumkin yoki shu yerda davom ettiriladi
    return await ask_for_registration_or_show_menu(update, context)  # Yangi holatga o'tish


async def start_registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """ "Ro'yxatdan o'tish / Kirish" tugmasi bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()  # Callback so'roviga javob berish
    lang_code = get_user_lang(context)
    user_id = query.from_user.id
    logger.info(f"User {user_id} initiated registration.")

    # Telefon raqamni so'raymiz
    button_text = "📱 Telefon raqamni yuborish" if lang_code == 'uz' else "📱 Отправить номер телефона"
    # request_contact=True tugmasi bosilganda Telegram kontakt yuborishni so'raydi
    keyboard = [[KeyboardButton(button_text, request_contact=True)]]
    # one_time_keyboard=True - tugma bir marta bosilgandan keyin klaviatura yopiladi
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    message_text = "Iltimos, quyidagi tugma orqali Telegramga ulangan telefon raqamingizni yuboring:" if lang_code == 'uz' else "Пожалуйста, отправьте свой номер телефона, привязанный к Telegram, с помощью кнопки ниже:"

    try:
        # Avvalgi xabardagi inline tugmalarni olib tashlab, matnni yangilaymiz
        await query.edit_message_text(text=message_text)
    except Exception as e:
        # Agar xabarni tahrirlab bo'lmasa (masalan, eski bo'lsa), yangi xabar yuboramiz
        logger.warning(f"Could not edit registration start message: {e}")
        await context.bot.send_message(chat_id=user_id, text=message_text)

    # Foydalanuvchiga "Kontakt yuborish" tugmasini ko'rsatish uchun kichik yordamchi xabar
    # Bu reply_markup'ni aktivlashtiradi
    await query.message.reply_text(
        text="👇",
        reply_markup=reply_markup
    )

    return WAITING_PHONE  # Telefon raqamini kutish holatiga o'tamiz


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Foydalanuvchi kontaktini (telefon raqamini) qabul qiladi."""
    contact = update.message.contact
    user = update.effective_user
    phone_number = contact.phone_number
    telegram_id = user.id
    first_name = user.first_name
    last_name = user.last_name
    lang_code = get_user_lang(context)  # Assumes get_user_lang helper exists

    # Telefon raqamiga + qo'shish (agar kerak bo'lsa)
    if not phone_number.startswith('+'):
        phone_number = '+' + phone_number
    logger.info(f"Received contact from {telegram_id}: {phone_number}")

    # Telefon raqamini keyingi qadam (OTP tekshirish) uchun saqlab qo'yamiz
    context.user_data['registration_phone_number'] = phone_number
    logger.debug(f"Stored phone number {phone_number} in user_data for user {telegram_id}")  # Debug log

    # API ga yuborish uchun ma'lumotlar
    registration_data = {
        "telegram_id": telegram_id,
        "phone_number": phone_number,
        "first_name": first_name,
        "last_name": last_name or "",
        # username is optional
    }

    # Register API'ni chaqiramiz (make_api_request yordamida)
    # make_api_request funksiyasi telegram_id ni user_id sifatida qabul qiladi
    api_response = await make_api_request(context, 'POST', 'auth/register/', telegram_id, data=registration_data)

    if api_response and not api_response.get('error'):
        # API muvaffaqiyatli javob berdi (OTP yuborilgani haqida xabar)
        logger.info(f"Registration request successful for {telegram_id}, OTP 'sent' via Telegram message.")
        message_text = "Rahmat! Tasdiqlash kodi Telegram orqali sizga yuborildi. Iltimos, kodni shu yerga kiriting:" if lang_code == 'uz' else "Спасибо! Код подтверждения отправлен вам в Telegram. Пожалуйста, введите код здесь:"
        await update.message.reply_text(message_text,
                                        reply_markup=ReplyKeyboardRemove())  # Kontakt yuborish tugmasini olib tashlaymiz
        return WAITING_OTP  # OTP kodni kutish holatiga o'tamiz
    else:
        # API xatolik qaytardi yoki network xatosi bo'ldi
        error_detail = api_response.get('detail',
                                        'Noma\'lum server xatoligi') if api_response else 'Server bilan bog\'lanish xatosi'
        status_code = api_response.get('status_code', 500) if api_response else 500
        logger.warning(f"Registration API error for {telegram_id}: Status {status_code} - {error_detail}")
        # Foydalanuvchiga tushunarli xabar berish
        if "allaqachon aktiv" in str(error_detail).lower():
            error_text = "Bu raqam allaqachon ro'yxatdan o'tgan va aktiv." if lang_code == 'uz' else "Этот номер уже зарегистрирован и активен."
        elif "boshqa foydalanuvchi" in str(error_detail).lower():  # Agar TG ID xatoligini qo'shgan bo'lsak
            error_text = "Xatolik: Telegram ID yoki telefon raqami boshqa foydalanuvchiga tegishli." if lang_code == 'uz' else "Ошибка: Telegram ID или номер телефона принадлежат другому пользователю."
        else:
            error_text = f"Xatolik yuz berdi ({str(error_detail)[:50]}...). Iltimos, qaytadan urinish uchun /start bosing." if lang_code == 'uz' else f"Произошла ошибка ({str(error_detail)[:50]}...). Нажмите /start, чтобы попробовать снова."

        await update.message.reply_text(error_text, reply_markup=ReplyKeyboardRemove())
        # Vaqtinchalik ma'lumotni tozalash
        if 'registration_phone_number' in context.user_data: del context.user_data['registration_phone_number']
        return ConversationHandler.END  # Suhbatni tugatamiz


async def otp_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Foydalanuvchi kiritgan OTP kodni qabul qiladi va tekshiradi."""
    user = update.effective_user
    user_id = user.id
    otp_code = update.message.text
    lang_code = get_user_lang(context)  # Tilni olamiz

    # Kiritilgan kodni sodda tekshirish (masalan, 4-6 xonali raqam)
    if not re.match(r'^\d{4,6}$', otp_code):
        error_text = "Noto'g'ri formatdagi kod. Iltimos, 4-6 xonali raqam kiriting." if lang_code == 'uz' else "Неверный формат кода. Пожалуйста, введите 4-6 значный код."
        await update.message.reply_text(error_text)
        # Xato format bo'lsa, yana OTP kutish holatida qolamiz
        return WAITING_OTP

    # Oldingi qadamda saqlangan telefon raqamini user_data dan olamiz
    phone_number = context.user_data.get('registration_phone_number')
    if not phone_number:
        logger.error(f"Cannot verify OTP for user {user_id}: phone number not found in user_data.")
        error_text = "Xatolik yuz berdi (Ichki ma'lumot topilmadi). Iltimos, /start buyrug'i bilan qayta boshlang." if lang_code == 'uz' else "Произошла ошибка (Внутренние данные не найдены). Пожалуйста, начните заново с /start."
        await update.message.reply_text(error_text, reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END  # Jarayonni tugatamiz

    logger.info(f"Received OTP {otp_code} for phone {phone_number} from user {user_id}")

    # API'ning verify endpoint'ini chaqiramiz
    verification_data = {
        "phone_number": phone_number,
        "otp_code": otp_code
    }
    # make_api_request til sarlavhasini va kerak bo'lsa token sarlavhasini (bu yerda shart emas) qo'shadi
    api_response = await make_api_request(context, 'POST', 'auth/verify/', user_id, data=verification_data)

    if api_response and not api_response.get('error'):
        # Muvaffaqiyatli javob keldi
        access_token = api_response.get('access_token')
        refresh_token = api_response.get('refresh_token')
        user_api_data = api_response.get('user')

        if access_token and refresh_token and user_api_data:
            # Tokenlarni kontekst/persistence ga saqlaymiz
            await store_user_token_data(context, user_id, access_token, refresh_token)

            # Tilni DB ga yozishga harakat qilamiz (agar user_data da bo'lsa)
            lang_to_save = context.user_data.get('language_code')
            if lang_to_save:
                await update_language_in_db(context, user_id, lang_to_save)

            success_text = "Muvaffaqiyatli! Siz tizimga kirdingiz." if lang_code == 'uz' else "Успешно! Вы вошли в систему."
            await update.message.reply_text(success_text,
                                            reply_markup=get_main_menu_markup(context))  # Asosiy menyuni chiqaramiz

            # Vaqtinchalik telefon raqamni user_data dan o'chiramiz
            if 'registration_phone_number' in context.user_data:
                del context.user_data['registration_phone_number']
            return MAIN_MENU  # Asosiy menyu holatiga o'tamiz
        else:
            # API dan kutilgan javob kelmadi
            logger.error(f"Invalid response structure from /auth/verify/ for user {user_id}: {api_response}")
            error_text = "Tizimdan javob olishda xatolik." if lang_code == 'uz' else "Ошибка при получении ответа от системы."
            await update.message.reply_text(error_text)
            # Qayta urinishga imkon beramizmi yoki tugatamizmi? Hozircha qayta urinish uchun shu holatda qolamiz.
            return WAITING_OTP
    else:
        # API xatolik qaytardi (masalan, noto'g'ri kod) yoki network xatosi
        error_detail = api_response.get('detail',
                                        'Noma\'lum xatolik') if api_response else 'Server bilan bog\'lanish xatosi'
        status_code = api_response.get('status_code', 500) if api_response else 500
        logger.warning(f"OTP Verification API error for {user_id}: Status {status_code} - {error_detail}")

        # API dan kelgan xatolik xabarini ko'rsatamiz
        if "Noto'g'ri yoki muddati o'tgan" in str(error_detail):  # API xabariga moslash
            error_text = "Kiritilgan kod noto'g'ri yoki muddati o'tgan. Iltimos, qayta kiriting yoki /cancel buyrug'ini bering." if lang_code == 'uz' else "Введенный код неверный или истек. Пожалуйста, введите снова или нажмите /cancel."
        else:
            error_text = f"Xatolik: {str(error_detail)[:100]}" if lang_code == 'uz' else f"Ошибка: {str(error_detail)[:100]}"
        await update.message.reply_text(error_text)
        # Foydalanuvchiga qayta kod kiritish imkonini berish uchun shu holatda qolamiz
        return WAITING_OTP


# --- Autentifikatsiya Tekshiruvi va Keyingi Qadam ---
async def ask_for_registration_or_show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Til tanlangandan keyin ishlaydi, autentifikatsiyani tekshiradi."""
    user = update.effective_user  # CallbackQuery'dan kelsa ham ishlaydi
    user_id = user.id
    lang_code = get_user_lang(context)

    logger.info(f"Checking authentication for user {user_id}")
    # Haqiqiy tekshiruv logikasi keyingi qadamlarda qo'shiladi
    # Hozircha, har doim ro'yxatdan o'tishni so'raymiz deb faraz qilaylik
    is_authenticated = False  # Placeholder

    if is_authenticated:
        # ... (Asosiy menyuni ko'rsatish kodi keyin qo'shiladi) ...
        logger.info(f"User {user_id} is authenticated. Showing main menu.")
        welcome_text = "Asosiy menyu." if lang_code == 'uz' else "Главное меню."
        main_markup = main_menu_markup_ru if lang_code == 'ru' else main_menu_markup_uz
        await context.bot.send_message(chat_id=user_id, text=welcome_text, reply_markup=main_markup)
        return MAIN_MENU
    else:
        logger.info(f"User {user_id} is not authenticated. Prompting registration.")
        button_text = "Ro'yxatdan o'tish / Kirish" if lang_code == 'uz' else "Регистрация / Вход"
        keyboard = [[InlineKeyboardButton(button_text, callback_data='start_registration')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        prompt_text = "Davom etish uchun tizimga kirishingiz yoki ro'yxatdan o'tishingiz kerak." if lang_code == 'uz' else "Для продолжения необходимо войти или зарегистрироваться."
        # await context.bot.send_message(chat_id=user_id, text=prompt_text, reply_markup=reply_markup)
        # Til tanlash xabarini tahrirlaymiz (agar callbackdan kelgan bo'lsa)
        if update.callback_query:
            await update.callback_query.edit_message_text(text=prompt_text, reply_markup=reply_markup)
        else:  # Agar /start dan keyin to'g'ridan to'g'ri chaqirilsa (kelajakda)
            await update.message.reply_text(text=prompt_text, reply_markup=reply_markup)

        # Bu yerda hali holat o'zgarmaydi, ro'yxatdan o'tish tugmasi bosilishini kutamiz
        return AUTH_CHECK  # Yangi holat: Autentifikatsiyani kutish/Ro'yxatdan o'tishni boshlash


# --- Suhbatni Bekor Qilish (Placeholder) ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Suhbatni bekor qiladi."""
    user = update.effective_user
    lang_code = get_user_lang(context)
    logger.info(f"User {user.id} canceled the conversation.")
    cancel_text = "Amal bekor qilindi." if lang_code == 'uz' else "Действие отменено."
    await update.message.reply_text(cancel_text, reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()  # Kontekstni tozalash
    return ConversationHandler.END  # Suhbatni tugatish


async def main_menu_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Asosiy menyu holatidagi matnli xabarlarni (tugmalarni) boshqaradi."""
    user = update.effective_user
    user_id = user.id
    lang_code = get_user_lang(context)
    message_text = update.message.text
    logger.info(f"Received main menu command '{message_text}' from user {user_id}")

    reply_text = ""  # Default reply text if no specific action is taken
    next_state = MAIN_MENU  # Stay in main menu by default

    # Qaysi menyu tugmasi bosilganini tekshiramiz
    if message_text in ["🍽️ Menyu", "🍽️ Меню"]:
        # Kategoriyalarni API dan olamiz
        loading_text = "Kategoriyalar yuklanmoqda..." if lang_code == 'uz' else "Загрузка категорий..."
        # Send loading message immediately
        await update.message.reply_text(loading_text)

        categories_response = await make_api_request(context, 'GET', 'categories/', user_id)

        if categories_response and not categories_response.get('error'):
            categories = categories_response.get('results', [])
            if categories:
                keyboard = []
                for category in categories:
                    button = InlineKeyboardButton(
                        category.get('name', 'N/A'),  # Use .get for safety
                        callback_data=f"cat_{category.get('id')}"
                    )
                    keyboard.append([button])

                reply_markup = InlineKeyboardMarkup(keyboard)
                response_text = "Kategoriyalardan birini tanlang:" if lang_code == 'uz' else "Выберите одну из категорий:"
                # Send the categories with the keyboard
                await update.message.reply_text(response_text, reply_markup=reply_markup)
                # No need to return reply_text here as we sent the message
                return next_state  # Stay in main menu
            else:
                reply_text = "Kategoriyalar topilmadi." if lang_code == 'uz' else "Категории не найдены."
        else:
            # API error handling
            error_detail = categories_response.get('detail',
                                                   'Noma\'lum xatolik') if categories_response else 'Server bilan bog\'lanish xatosi'
            reply_text = f"Kategoriyalarni olib bo'lmadi: {error_detail}" if lang_code == 'uz' else f"Не удалось получить категории: {error_detail}"
        # If we fall through here, send the reply_text
        await update.message.reply_text(reply_text)
        return next_state

    elif message_text in ["🛒 Savat", "🛒 Корзина"]:
        reply_text = "Savat bo'limi..." if lang_code == 'uz' else "Раздел Корзина..."
        # TODO: Call GET /cart/ API and display cart contents
        await update.message.reply_text(reply_text)  # Send placeholder reply
        return next_state

    elif message_text in ["📋 Buyurtmalarim", "📋 Мои заказы"]:
        reply_text = "Buyurtmalar tarixi..." if lang_code == 'uz' else "История заказов..."
        # TODO: Call GET /orders/history/ API and display history
        await update.message.reply_text(reply_text)
        return next_state

    elif message_text in ["📍 Filiallar", "📍 Филиалы"]:
        reply_text = "Filiallar ro'yxati..." if lang_code == 'uz' else "Список филиалов..."
        # TODO: Call GET /branches/ API and display branches
        await update.message.reply_text(reply_text)
        return next_state

    elif message_text in ["👤 Profil", "👤 Профиль"]:
        reply_text = "Profil ma'lumotlari..." if lang_code == 'uz' else "Данные профиля..."
        # TODO: Call GET /users/profile/ API and display profile
        await update.message.reply_text(reply_text)
        return next_state

    elif message_text in ["⚙️ Sozlamalar", "⚙️ Настройки"]:
        reply_text = "Tilni o'zgartirish uchun /start buyrug'ini qayta bosing." \
            if lang_code == 'uz' else \
            "Чтобы изменить язык, нажмите /start снова."
        await update.message.reply_text(reply_text)
        return next_state

    else:
        # Handle unrecognized text in main menu state
        reply_text = "Noma'lum buyruq. Iltimos, menyudagi tugmalardan birini bosing." if lang_code == 'uz' else "Неизвестная команда. Пожалуйста, используйте кнопки меню."
        await update.message.reply_text(reply_text)
        return next_state


async def category_selected_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Kategoriya tugmasi bosilganda ishlaydi."""
    query = update.callback_query
    await query.answer()  # Callbackga javob beramiz
    user_id = query.from_user.id
    lang_code = get_user_lang(context)

    # callback_data dan kategoriya ID sini ajratib olamiz ('cat_<ID>')
    try:
        category_id = int(query.data.split('_')[1])
    except (IndexError, ValueError):
        logger.warning(f"Invalid callback data received: {query.data}")
        await query.edit_message_text("Xatolik: Noto'g'ri kategoriya tanlandi.")
        return

    logger.info(f"User {user_id} selected category ID: {category_id}")

    # Mahsulotlarni yuklash xabarini chiqaramiz
    loading_text = "Mahsulotlar yuklanmoqda..." if lang_code == 'uz' else "Загрузка продуктов..."
    await query.edit_message_text(text=loading_text)  # Oldingi tugmalarni olib tashlaymiz

    # API dan mahsulotlarni olamiz
    products_response = await make_api_request(context, 'GET', f'products/?category_id={category_id}', user_id)

    if products_response and not products_response.get('error'):
        products = products_response.get('results', [])
        if products:
            # --- Tugmalar qismi o'zgaradi ---
            keyboard = []  # Inline tugmalar uchun bo'sh massiv
            message_text = f"--- {products[0].get('category', {}).get('name', '')} ---\n\n" if products else "Mahsulotlar:\n\n"

            for product in products:
                product_text = f"<b>{product.get('name', 'Nomsiz')}</b>\n"
                description = product.get('description')
                if description:
                    product_text += f"<pre>{description}</pre>\n"
                product_text += f"Narxi: {product.get('price', 'N/A')} so'm"
                message_text += product_text + "\n"  # Matn qismi

                # Har bir mahsulot uchun alohida qatorda "Savatga qo'shish" tugmasi
                add_button_text = "🛒 Savatga" if lang_code == 'uz' else "🛒 В корзину"
                keyboard.append([
                    InlineKeyboardButton(
                        f"{add_button_text} ({product.get('name', '')[:15]}...)",  # Qisqa nom bilan
                        callback_data=f"add_{product.get('id')}"  # Callback data: add_<product_id>
                    )
                ])
                message_text += "--------------------\n"  # Ajratuvchi

            reply_markup = InlineKeyboardMarkup(keyboard)
            # Xabarni tahrirlaymiz yoki yangi yuboramiz
            try:
                await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            except Exception as e:  # Agar xabar o'zgarmagan bo'lsa (masalan, matn bir xil)
                logger.warning(f"Could not edit product list message, sending new: {e}")
                await context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup,
                                               parse_mode=ParseMode.HTML)
        else:
            reply_text = "Bu kategoriyada mahsulotlar topilmadi." if lang_code == 'uz' else "В этой категории товары не найдены."
            await query.edit_message_text(text=reply_text)
    else:
        error_detail = products_response.get('detail',
                                             'Noma\'lum xatolik') if products_response else 'Server bilan bog\'lanish xatosi'
        reply_text = f"Mahsulotlarni olib bo'lmadi: {error_detail}" if lang_code == 'uz' else f"Не удалось получить товары: {error_detail}"
        await query.edit_message_text(text=reply_text)


# --- Asosiy 'main' funksiya ---
def main() -> None:
    """Botni ishga tushuradi va sozlaydi."""

    # Persistence sozlamasi (user_data va conversation holatlarini saqlash uchun)
    persistence = PicklePersistence(filepath="bot_storage.pickle")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .persistence(persistence)  # <-- Persistence qo'shildi
        .build()
    )

    # Asosiy ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_LANG: [
                CallbackQueryHandler(set_language_callback, pattern='^set_lang_')
            ],
            AUTH_CHECK: [
                # Bu holatda "Ro'yxatdan o'tish / Kirish" tugmasini kutamiz
                CallbackQueryHandler(start_registration_callback, pattern='^start_registration$')
                # Agar foydalanuvchi boshqa narsa yozsa yoki /start bossa? Fallback hal qiladi.
            ],
            WAITING_PHONE: [
                MessageHandler(filters.CONTACT & ~filters.COMMAND, contact_handler)
                # TODO: Add handler for text message if user types instead of sharing contact?
            ],
            WAITING_OTP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r'^\d{4,6}$'), otp_handler),
                # TODO: Handle incorrect OTP format? Add a separate handler.
            ],
            MAIN_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_dispatch)
                # TODO: Add handlers for main menu button clicks
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start)  # Istalgan holatda /start boshiga qaytaradi
        ],
        name="main_conversation",
        persistent=True,  # Holatlarni saqlash uchun
    )

    application.add_handler(conv_handler)

    application.add_handler(CallbackQueryHandler(category_selected_callback, pattern='^cat_'))

    # Botni ishga tushirish
    logger.info("Starting bot...")
    application.run_polling()

    # TODO: Add graceful shutdown for api_client if needed using asyncio
    # Example (might need adjustments):
    # loop = asyncio.get_event_loop()
    # try:
    #     loop.run_until_complete(api_client.aclose())
    # finally:
    #     loop.close()


if __name__ == "__main__":
    main()
