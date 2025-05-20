# bot/keyboards.py
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton
import logging

logger = logging.getLogger(__name__)

# --- Asosiy Menyu Klaviaturalari ---
main_menu_keyboard_uz = [
    ["🍽️ Menyu", "🛒 Savat"],
    ["📋 Buyurtmalarim", "📍 Filiallar"],
    ["🎁 Aksiyalar", "👤 Profil"],
    ["⚙️ Sozlamalar"]
]
main_menu_keyboard_ru = [
    ["🍽️ Меню", "🛒 Корзина"],
    ["📋 Мои заказы", "📍 Филиалы"],
    ["🎁 Акции", "👤 Профиль"],
    ["⚙️ Настройки"]
]
main_menu_markup_uz = ReplyKeyboardMarkup(main_menu_keyboard_uz, resize_keyboard=True)
main_menu_markup_ru = ReplyKeyboardMarkup(main_menu_keyboard_ru, resize_keyboard=True)


def get_main_menu_markup(context) -> ReplyKeyboardMarkup:  # context qabul qiladi
    """Tilga mos asosiy menyu klaviaturasini qaytaradi."""
    # get_user_lang ni import qilish kerak bo'ladi, agar contextda user_id bo'lsa
    # Hozircha get_user_lang ni helpers.py dan chaqiramiz
    from .utils.helpers import get_user_lang  # Siklik import bo'lmasligi uchun ehtiyot bo'ling

    lang_code = get_user_lang(context)
    logger.info(f"GET_MAIN_MENU_MARKUP: Detected language_code = '{lang_code}'")  # <-- LOG QO'SHING
    if lang_code == 'ru':
        logger.info("GET_MAIN_MENU_MARKUP: Returning Russian keyboard.")  # <-- LOG QO'SHING
        return main_menu_markup_ru
    else:
        logger.info("GET_MAIN_MENU_MARKUP: Returning Uzbek keyboard.")  # <-- LOG QO'SHING
        return main_menu_markup_uz


# --- Til Tanlash Klaviaturasi ---
def get_language_keyboard() -> InlineKeyboardMarkup:
    """Til tanlash uchun inline klaviatura qaytaradi."""
    keyboard = [
        [
            InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data='set_lang_uz'),
            InlineKeyboardButton("🇷🇺 Русский", callback_data='set_lang_ru'),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# --- Registratsiya Boshlash Klaviaturasi ---
def get_registration_keyboard(lang_code: str) -> InlineKeyboardMarkup:
    """Ro'yxatdan o'tishni boshlash tugmasini qaytaradi."""
    button_text = "Ro'yxatdan o'tish / Kirish" if lang_code == 'uz' else "Регистрация / Вход"
    keyboard = [[InlineKeyboardButton(button_text, callback_data='start_registration')]]
    return InlineKeyboardMarkup(keyboard)


# --- Telefon Raqam So'rash Klaviaturasi ---
def get_phone_keyboard(lang_code: str) -> ReplyKeyboardMarkup:
    """Kontakt yuborish tugmasini qaytaradi."""
    button_text = "📱 Telefon raqamni yuborish" if lang_code == 'uz' else "📱 Отправить номер телефона"
    keyboard = [[KeyboardButton(button_text, request_contact=True)]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_product_detail_keyboard(product_id: int, category_id: int | None, quantity: int,
                                lang_code: str) -> InlineKeyboardMarkup:
    """Mahsulot detallari sahifasi uchun inline klaviatura yaratadi."""
    minus_button = InlineKeyboardButton("➖", callback_data=f"pdetail_decr_{product_id}")
    # Miqdor tugmasi hozircha bosilmaydi, shunchaki ko'rsatadi
    qty_button = InlineKeyboardButton(str(quantity), callback_data=f"pdetail_qty_{product_id}")
    plus_button = InlineKeyboardButton("➕", callback_data=f"pdetail_incr_{product_id}")

    add_cart_button_text = "🛒 Savatga" if lang_code == 'uz' else "🛒 В корзину"
    # product_id ni add callbackiga ham qo'shamiz
    add_cart_button = InlineKeyboardButton(add_cart_button_text, callback_data=f"pdetail_add_{product_id}")

    back_button_text = "< Ortga" if lang_code == 'uz' else "< Назад"
    back_button_callback = f"back_to_prod_list_{category_id}" if category_id else "back_to_categories"
    back_button = InlineKeyboardButton(back_button_text, callback_data=back_button_callback)

    keyboard = [
        [minus_button, qty_button, plus_button],
        [add_cart_button],
        [back_button]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Boshqa klaviaturalar uchun funksiyalar shu yerga qo'shilishi mumkin ---
# Masalan, kategoriya tugmalarini yasash, mahsulot tugmalarini yasash va h.k.
