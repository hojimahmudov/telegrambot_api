# bot/keyboards.py
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton

# --- Asosiy Menyu Klaviaturalari ---
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


def get_main_menu_markup(lang_code: str) -> ReplyKeyboardMarkup:
    """Tilga mos asosiy menyu klaviaturasini qaytaradi."""
    return main_menu_markup_ru if lang_code == 'ru' else main_menu_markup_uz


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

# --- Boshqa klaviaturalar uchun funksiyalar shu yerga qo'shilishi mumkin ---
# Masalan, kategoriya tugmalarini yasash, mahsulot tugmalarini yasash va h.k.
