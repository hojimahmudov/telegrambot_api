# bot/utils/db_utils.py
import sqlite3
import logging
import os

logger = logging.getLogger(__name__)
# Ma'lumotlar bazasi fayli loyiha root papkasida (manage.py bilan bir joyda) yaratiladi
DB_NAME = "bot_user_data.sqlite"
# __file__ -> bot/utils/db_utils.py
# os.path.dirname(__file__) -> bot/utils
# os.path.dirname(os.path.dirname(__file__)) -> bot
# os.path.dirname(os.path.dirname(os.path.dirname(__file__))) -> loyiha root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(PROJECT_ROOT, DB_NAME)


def get_db_connection():
    """Ma'lumotlar bazasiga ulanishni qaytaradi."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # Ustunlarga nomi orqali murojaat qilish uchun
        return conn
    except sqlite3.Error as e:
        logger.error(f"SQLite connection error: {e}", exc_info=True)
        raise  # Xatolikni yuqoriga uzatamiz


def init_db():
    """Ma'lumotlar bazasini yaratadi va 'user_settings' jadvalini tuzadi (agar mavjud bo'lmasa)."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    telegram_id INTEGER PRIMARY KEY,
                    access_token TEXT,
                    refresh_token TEXT,
                    language_code TEXT
                )
            """)
            conn.commit()
            logger.info(f"Database initialized/checked at {DB_PATH}")
    except sqlite3.Error as e:
        logger.error(f"Database error during init_db: {e}", exc_info=True)


def save_user_session_data(telegram_id: int, access_token: str = None, refresh_token: str = None,
                           language_code: str = None):
    """Foydalanuvchi sessiyasi ma'lumotlarini (tokenlar, til) saqlaydi yoki yangilaydi."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Avval mavjud yozuvni tekshiramiz
            cursor.execute("SELECT 1 FROM user_settings WHERE telegram_id = ?", (telegram_id,))
            exists = cursor.fetchone()

            if exists:
                # Yangilash uchun faqat berilgan parametrlarni olamiz
                updates = {}
                if access_token is not None: updates['access_token'] = access_token
                if refresh_token is not None: updates['refresh_token'] = refresh_token
                if language_code is not None: updates['language_code'] = language_code

                if updates:  # Agar yangilash uchun biror narsa bo'lsa
                    set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
                    params = list(updates.values()) + [telegram_id]
                    cursor.execute(f"UPDATE user_settings SET {set_clause} WHERE telegram_id = ?", tuple(params))
                    logger.info(f"Updated session data for user {telegram_id}: {list(updates.keys())}")
                else:
                    logger.info(f"No specific fields to update for user {telegram_id}, data remains.")
            else:
                # Yangi yozuv qo'shamiz
                cursor.execute("""
                    INSERT INTO user_settings (telegram_id, access_token, refresh_token, language_code)
                    VALUES (?, ?, ?, ?)
                """, (telegram_id, access_token, refresh_token, language_code))
                logger.info(f"Inserted new session data for user {telegram_id}")
            conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error saving session data for user {telegram_id}: {e}", exc_info=True)


def get_user_session_data(telegram_id: int) -> dict | None:
    """Foydalanuvchi uchun sessiya ma'lumotlarini (tokenlar, til) oladi."""
    data = None
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT access_token, refresh_token, language_code FROM user_settings WHERE telegram_id = ?",
                           (telegram_id,))
            row = cursor.fetchone()
            if row:
                data = {'access': row['access_token'], 'refresh': row['refresh_token'], 'lang': row['language_code']}
                logger.debug(f"Retrieved session data for user {telegram_id} from DB.")
            else:
                logger.debug(f"No session data found in DB for user {telegram_id}")
    except sqlite3.Error as e:
        logger.error(f"Database error getting session data for user {telegram_id}: {e}", exc_info=True)
    return data


def clear_user_session_data(telegram_id: int):
    """Foydalanuvchi uchun barcha sessiya ma'lumotlarini o'chiradi."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_settings WHERE telegram_id = ?", (telegram_id,))
            conn.commit()
            logger.info(f"Cleared all session data from DB for user {telegram_id}")
    except sqlite3.Error as e:
        logger.error(f"Database error clearing session data for user {telegram_id}: {e}", exc_info=True)
