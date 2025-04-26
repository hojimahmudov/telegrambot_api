# bot/utils/api_client.py
import httpx
import time
import logging
import json
from telegram.ext import ContextTypes
from ..config import API_BASE_URL  # Konfiguratsiyadan URL ni olamiz
from .helpers import get_user_lang, get_user_token_data, clear_user_token_data  # Yordamchilarni import qilamiz

logger = logging.getLogger(__name__)

# API Klienti (global yoki class ichida bo'lishi mumkin)
api_client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=20.0)


async def make_api_request(context: ContextTypes.DEFAULT_TYPE, method: str, endpoint: str, user_id: int,
                           data: dict = None, params: dict = None) -> dict | None:
    """API ga autentifikatsiya va til sarlavhasi bilan so'rov yuboradi."""
    token_data = await get_user_token_data(context, user_id)
    lang_code = get_user_lang(context)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Language": lang_code
    }
    if token_data and token_data.get('access'):
        headers["Authorization"] = f"Bearer {token_data['access']}"
        logger.debug(f"Using token for user {user_id} for request to {endpoint}")
    else:
        logger.debug(f"No token found or used for user {user_id} for request to {endpoint}")

    try:
        logger.debug(f"API Request -> {method} {endpoint} ...")
        start_time = time.monotonic()  # <-- Vaqtni belgilaymiz

        response = await api_client.request(method, endpoint, headers=headers, json=data, params=params)

        end_time = time.monotonic()  # <-- Vaqtni belgilaymiz
        duration = end_time - start_time
        logger.info(f"API call to {endpoint} took {duration:.4f} seconds.")  # <-- Vaqtni logga chiqaramiz

        logger.debug(f"API Response Status <- {method} {endpoint}: {response.status_code}")

        if response.status_code == 204: return {"success": True, "status_code": response.status_code}

        try:
            response_data = response.json()
        except json.JSONDecodeError:
            if 200 <= response.status_code < 300:
                logger.warning(f"API {endpoint} succeeded ({response.status_code}) but non-JSON body.")
                return {"success": True, "status_code": response.status_code, "detail": response.text}
            else:
                response.raise_for_status()
                return {"error": "Invalid Response Format", "detail": response.text,
                        "status_code": response.status_code}

        response.raise_for_status()
        response_data['status_code'] = response.status_code
        return response_data

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        error_text = e.response.text
        logger.error(f"API HTTP Error for {user_id} at {endpoint}: {status_code} - {error_text}")
        try:
            error_data = e.response.json()
        except json.JSONDecodeError:
            error_data = {"detail": error_text}

        if status_code == 401 and token_data:
            logger.info(f"Access token expired/invalid for user {user_id}. Clearing.")
            await clear_user_token_data(context, user_id)
            error_message = "Sessiya muddati tugadi. /start bosing." if lang_code == 'uz' else "Сессия истекла. Нажмите /start."
            return {"error": "Unauthorized", "detail": error_message, "status_code": status_code}
        return {"error": f"API Error {status_code}",
                "detail": error_data.get('detail', error_data.get('error', error_text)), "status_code": status_code}
    except httpx.Timeout:
        logger.error(f"Timeout error for {user_id} at {endpoint}.")
        return {"error": "Timeout", "detail": "API javob bermadi.", "status_code": 504}
    except httpx.RequestError as e:
        logger.error(f"Network error for {user_id} at {endpoint}: {e}", exc_info=True)
        return {"error": "Network Error", "detail": "Server bilan bog'lanib bo'lmadi.", "status_code": 503}
    except Exception as e:
        logger.error(f"Unexpected error during API request for {user_id} at {endpoint}: {e}", exc_info=True)
        return {"error": "Unexpected Error", "detail": str(e), "status_code": 500}


# Tilni DB ga yozish funksiyasi API call qilgani uchun shu yerda bo'lgani mantiqiyroq
async def update_language_in_db(context: ContextTypes.DEFAULT_TYPE, user_id: int, lang_code: str):
    logger.info(f"Attempting to update language to '{lang_code}' in DB for user {user_id}")
    profile_update_data = {"language_code": lang_code}
    api_response = await make_api_request(context, 'PATCH', 'users/profile/', user_id, data=profile_update_data)
    if api_response and not api_response.get('error'):
        logger.info(f"Successfully updated language preference in DB for user {user_id}")
    else:
        logger.warning(f"Failed to update language preference in DB for user {user_id}. Response: {api_response}")


async def close_api_client():
    """HTTPX klientni yopadi."""
    await api_client.aclose()
