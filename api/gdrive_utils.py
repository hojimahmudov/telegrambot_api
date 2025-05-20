# api/gdrive_utils.py
import os
import logging
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from django.conf import settings  # Django settings dan foydalanish uchun

logger = logging.getLogger(__name__)


def _get_drive_service():
    """Google Drive servisini autentifikatsiya qilib qaytaradi."""
    gauth = GoogleAuth()
    # Service account sozlamalari
    gauth.settings['client_config_backend'] = 'service'
    gauth.settings['service_config'] = {
        "client_json_file_path": settings.GOOGLE_DRIVE_CREDENTIALS_JSON_PATH,
        # Bu email service account'ingizniki bo'lishi shart emas,
        # lekin service account Drive'ga kirish huquqiga ega bo'lishi kerak.
        "client_user_email": "chocoberry@chocoberryimage.iam.gserviceaccount.com", # Bu shart emas service account uchun
    }
    gauth.ServiceAuth()  # Avtorizatsiya
    return GoogleDrive(gauth)


def upload_to_drive(local_file_path: str, drive_file_name: str, drive_folder_id: str = None) -> tuple[
    str | None, str | None]:
    """Faylni Google Drive'ga yuklaydi va uning IDsi hamda linkini qaytaradi."""
    try:
        if not os.path.exists(local_file_path):
            logger.error(f"File not found at path: {local_file_path}")
            return None, None

        drive = _get_drive_service()

        file_metadata = {'title': drive_file_name}
        if drive_folder_id:
            file_metadata['parents'] = [{'id': drive_folder_id}]  # Muayyan papkaga yuklash

        drive_file = drive.CreateFile(file_metadata)
        drive_file.SetContentFile(local_file_path)
        drive_file.Upload()  # Faylni yuklash

        # Faylni hamma uchun o'qishga ruxsat berish
        drive_file.InsertPermission({
            'type': 'anyone',
            'value': 'anyone',
            'role': 'reader'
        })

        file_id = drive_file['id']
        # "uc?id=" linki ba'zan to'g'ridan-to'g'ri ko'rsatadi, "thumbnail" kichikroq preview uchun
        # Yaxshiroq link: drive_file['webContentLink'] yoki drive_file['webViewLink'] ni ham tekshirib ko'ring
        # Hozircha siz taklif qilgan linkni ishlatamiz:
        direct_link = f"https://drive.google.com/uc?export=view&id={file_id}"
        # Yoki: direct_link = drive_file.get('webContentLink') # Bu to'g'ridan-to'g'ri yuklab olish linki bo'lishi mumkin
        # Yoki: direct_link = drive_file.get('alternateLink') # Bu Drive ko'rish sahifasi

        logger.info(f"File '{drive_file_name}' uploaded to GDrive. ID: {file_id}, Link: {direct_link}")
        return file_id, direct_link
    except Exception as e:
        logger.error(f"Error uploading file '{drive_file_name}' to Google Drive: {e}", exc_info=True)
        return None, None  # Xatolik bo'lsa None qaytaramiz


def delete_from_drive(file_id: str):
    """Faylni Google Drive'dan ID si bo'yicha o'chiradi."""
    try:
        if not file_id:
            logger.warning("No file ID provided for deletion from GDrive.")
            return False

        drive = _get_drive_service()
        drive_file = drive.CreateFile({'id': file_id})
        drive_file.Delete()
        logger.info(f"File with ID {file_id} successfully deleted from Google Drive.")
        return True
    except Exception as e:
        logger.error(f"Error deleting file with ID {file_id} from Google Drive: {e}", exc_info=True)
        return False
