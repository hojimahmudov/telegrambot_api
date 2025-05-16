# bot/utils/api_client.py
import httpx
import time
import logging
import json
from telegram.ext import ContextTypes
from ..config import API_BASE_URL  # Konfiguratsiyadan URL ni olamiz
from .helpers import get_user_lang, get_user_token_data, clear_user_token_data, \
    store_user_token_data  # Yordamchilarni import qilamiz

logger = logging.getLogger(__name__)

# API Klienti (global yoki class ichida bo'lishi mumkin)
api_client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=20.0)


async def make_api_request(
        context: ContextTypes.DEFAULT_TYPE,
        method: str,
        endpoint: str,
        user_id: int,
        data: dict = None,
        params: dict = None,
        is_retry: bool = False  # Qayta urinish belgisi (cheksiz siklni oldini olish uchun)
) -> dict | None:
    token_data = await get_user_token_data(context, user_id)
    lang_code = get_user_lang(context)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Accept-Language": lang_code
    }

    current_access_token = None
    if token_data and token_data.get('access'):
        current_access_token = token_data['access']
        headers["Authorization"] = f"Bearer {current_access_token}"

    logger.debug(
        f"API Request -> {method} {api_client.base_url}{endpoint} Data: {data} Params: {params} IsRetry: {is_retry}")

    try:
        response = await api_client.request(method, endpoint, headers=headers, json=data, params=params)
        logger.debug(f"API Response Status <- {method} {endpoint}: {response.status_code}")

        if response.status_code == 204:
            return {"success": True, "status_code": response.status_code}
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            if 200 <= response.status_code < 300:
                return {"success": True, "status_code": response.status_code, "detail": response.text}
            else:
                response.raise_for_status()  # HTTPStatusError chaqiradi
                # Bu qatorga yetib kelmasligi kerak, lekin fallback
                return {"error": "Invalid Response Format", "detail": response.text,
                        "status_code": response.status_code}

        response.raise_for_status()  # 4xx va 5xx xatoliklar uchun
        response_data['status_code'] = response.status_code
        return response_data

    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        error_text_from_response = e.response.text
        logger.error(f"API HTTP Error for {user_id} at {endpoint}: {status_code} - {error_text_from_response}")

        # --- TOKEN YANGILASH LOGIKASI ---
        if status_code == 401 and current_access_token and not is_retry:
            logger.info(f"Access token for user {user_id} likely expired. Attempting refresh.")
            refresh_token = token_data.get('refresh')
            if refresh_token:
                try:
                    refresh_payload = {'refresh': refresh_token}
                    logger.info(f"Requesting new access token for user {user_id} using refresh token.")
                    # Token refresh uchun alohida, autentifikatsiyasiz so'rov
                    # api_client.base_url to'g'ri sozlangani muhim (http://127.0.0.1:8000/api/v1/)
                    refresh_api_endpoint = "auth/token/refresh/"  # API_BASE_URL ga nisbatan
                    token_refresh_response = await api_client.post(
                        refresh_api_endpoint,
                        json=refresh_payload,
                        headers={"Content-Type": "application/json", "Accept": "application/json"}
                    )
                    token_refresh_response.raise_for_status()  # Refresh xatosini ushlaymiz
                    new_token_data = token_refresh_response.json()
                    new_access_token = new_token_data.get('access')

                    if new_access_token:
                        logger.info(f"Token refreshed successfully for user {user_id}.")
                        # Yangi access token va eski refresh tokenni saqlaymiz
                        # (simplejwt odatda refreshni o'zgartirmaydi, lekin yangisini bersa uni ham saqlash kerak)
                        new_refresh_token = new_token_data.get('refresh', refresh_token)  # Agar yangi refresh kelsa
                        await store_user_token_data(context, user_id, new_access_token, new_refresh_token)

                        logger.info(f"Retrying original request to {endpoint} for user {user_id} with new token.")
                        # Asl so'rovni YANGI token bilan va is_retry=True qilib qayta chaqiramiz
                        return await make_api_request(context, method, endpoint, user_id, data, params, is_retry=True)
                    else:
                        logger.warning(f"Token refresh response did not contain new access token for user {user_id}.")
                except httpx.HTTPStatusError as refresh_err:
                    logger.error(
                        f"Failed to refresh token for user {user_id}. Status: {refresh_err.response.status_code}. Response: {refresh_err.response.text}")
                except Exception as refresh_e:
                    logger.error(f"Exception during token refresh for user {user_id}: {refresh_e}", exc_info=True)
            else:
                logger.warning(f"No refresh token found for user {user_id} to attempt refresh.")

            # Agar refresh muvaffaqiyatsiz bo'lsa yoki refresh token bo'lmasa, tokenni tozalab, xato qaytaramiz
            await clear_user_token_data(context, user_id)
            error_message = "Sessiya muddati tugadi. Iltimos, /start bosing." if lang_code == 'uz' else "Сессия истекла. Пожалуйста, нажмите /start."
            return {"error": "Unauthorized - Refresh Failed", "detail": error_message, "status_code": status_code}
        # --- TOKEN YANGILASH LOGIKASI TUGADI ---

        # Boshqa 4xx, 5xx xatoliklar uchun
        try:
            error_data = e.response.json()
        except json.JSONDecodeError:
            error_data = {"detail": error_text_from_response}
        return {"error": f"API Error {status_code}",
                "detail": error_data.get('detail', error_data.get('error', error_text_from_response)),
                "status_code": status_code}

    except httpx.Timeout:
        # ... (avvalgidek)
        logger.error(f"{user_id} uchun {endpoint} ga so'rovda Timeout xatoligi.")
        return {"error": "Timeout", "detail": "API javob bermadi.", "status_code": 504}
    except httpx.RequestError as e:
        # ... (avvalgidek)
        logger.error(f"{user_id} uchun {endpoint} ga so'rovda network xatoligi: {e}", exc_info=True)
        return {"error": "Network Error", "detail": "Server bilan bog'lanib bo'lmadi.", "status_code": 503}
    except Exception as e:
        # ... (avvalgidek)
        logger.error(f"{user_id} uchun {endpoint} ga so'rovda noma'lum xatolik: {e}", exc_info=True)
        return {"error": "Unexpected Error", "detail": str(e), "status_code": 500}


# Tilni DB ga yozish funksiyasi API call qilgani uchun shu yerda bo'lgani mantiqiyroq
async def update_language_in_db_api(context: ContextTypes.DEFAULT_TYPE, user_id: int, lang_code: str) -> bool:
    """Foydalanuvchi tilini API orqali backendda yangilaydi."""
    logger.info(f"Attempting to update language to '{lang_code}' in API for user {user_id}")
    profile_update_data = {"language_code": lang_code}
    api_response = await make_api_request(context, 'PATCH', 'users/profile/', user_id, data=profile_update_data)

    if api_response and not api_response.get('error'):
        logger.info(f"Successfully updated language in API for user {user_id}")
        return True
    else:
        logger.warning(f"Failed to update language in API for user {user_id}. Response: {api_response}")
        return False


async def close_api_client():
    """HTTPX klientni yopadi."""
    await api_client.aclose()
