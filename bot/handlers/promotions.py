# bot/handlers/promotions.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from ..utils.helpers import get_user_lang
from ..utils.api_client import make_api_request

logger = logging.getLogger(__name__)


async def show_promotions_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """API dan aktiv aksiyalarni oladi va foydalanuvchiga ko'rsatadi."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang_code = get_user_lang(context)

    # message obyektini olish (bu funksiya ReplyKeyboard tugmasidan chaqiriladi)
    message = update.message

    loading_text = "Aksiyalar yuklanmoqda..." if lang_code == 'uz' else "Загрузка акций..."
    await message.reply_text(loading_text)  # Foydalanuvchiga javob beramiz

    promotions_response = await make_api_request(context, 'GET', 'promotions/', user_id)  # Token shart emas bunga

    if promotions_response and not promotions_response.get('error'):
        promotions = promotions_response.get('results', [])
        if promotions:
            if lang_code == 'uz':
                await context.bot.send_message(chat_id=chat_id, text="🔥 <b>Aktiv Aksiyalar:</b>",
                                               parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(chat_id=chat_id, text="🔥 <b>Активные Акции:</b>",
                                               parse_mode=ParseMode.HTML)

            for promo in promotions:
                title = promo.get('title', 'N/A')  # Serializer'dan keladigan tarjima qilingan nom
                description = promo.get('description', '')
                image_url = promo.get('image_url')  # API URL to'liq bo'lishi kerak (MEDIA_URL bilan)

                message_text = f"<b>{title}</b>\n"
                if description:
                    message_text += f"<pre>{description}</pre>"  # Tavsifni yaxshiroq formatlash

                if image_url:
                    try:
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=image_url,
                            caption=message_text,
                            parse_mode=ParseMode.HTML
                            # TODO: Aksiya bilan bog'liq tugma qo'shish mumkin (masalan, "Batafsil" yoki "Mahsulotlarga o'tish")
                            # reply_markup=InlineKeyboardMarkup(...)
                        )
                    except Exception as e:
                        logger.error(f"Failed to send promotion photo {image_url}: {e}. Sending as text.")
                        # Rasm bilan yuborishda xatolik bo'lsa, matnni o'zini yuboramiz
                        await context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode=ParseMode.HTML)
                else:
                    # Rasm bo'lmasa, faqat matnni yuboramiz
                    await context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode=ParseMode.HTML)

            # Yuklanmoqda xabarini o'chirish shart emas, chunki javoblar yangi xabar bo'lib kelyapti
            # Agar loading_text ni edit qilmoqchi bo'lsak, boshqacha yondashuv kerak

        else:
            no_promotions_text = "Hozircha aktiv aksiyalar mavjud emas." if lang_code == 'uz' else "Активных акций пока нет."
            await context.bot.send_message(chat_id=chat_id, text=no_promotions_text)
    else:
        error_detail = promotions_response.get('detail',
                                               'Noma\'lum xatolik') if promotions_response else 'Server bilan bog\'lanish xatosi'
        reply_text = f"Aksiyalarni yuklashda xatolik: {error_detail}" if lang_code == 'uz' else f"Ошибка загрузки акций: {error_detail}"
        logger.error(f"Failed to fetch promotions: {error_detail}")
        await context.bot.send_message(chat_id=chat_id, text=reply_text)
