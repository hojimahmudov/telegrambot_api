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
        "client_user_email": "chocoberry@chocoberryimage.iam.gserviceaccount.com",
        # Bu shart emas service account uchun
    }
    gauth.ServiceAuth()  # Avtorizatsiya
    return GoogleDrive(gauth)


def upload_to_drive(local_file_path: str, drive_file_name: str, drive_folder_id: str = None) -> tuple[
    str | None, str | None]:
    try:
        logger.info(f"GDRIVE_UTIL: Starting upload. Local path: '{local_file_path}', Drive name: '{drive_file_name}'")
        if not os.path.exists(local_file_path):
            logger.error(f"GDRIVE_UTIL: File not found at path: {local_file_path}")
            return None, None

        drive = _get_drive_service()
        logger.info("GDRIVE_UTIL: Drive service obtained.")

        file_metadata = {'title': drive_file_name}
        if drive_folder_id:
            file_metadata['parents'] = [{'id': drive_folder_id}]

        drive_file = drive.CreateFile(file_metadata)
        logger.info(f"GDRIVE_UTIL: Drive file object created. Title: {drive_file['title']}")

        logger.info(f"GDRIVE_UTIL: Setting content from file: {local_file_path}")
        drive_file.SetContentFile(local_file_path)

        logger.info("GDRIVE_UTIL: Starting file upload to Drive...")
        drive_file.Upload()
        logger.info("GDRIVE_UTIL: File upload complete.")

        logger.info("GDRIVE_UTIL: Setting 'anyone with link can read' permission.")
        drive_file.InsertPermission({'type': 'anyone', 'value': 'anyone', 'role': 'reader'})
        logger.info("GDRIVE_UTIL: Permissions set.")

        file_id = drive_file['id']
        direct_link = f"https://drive.google.com/uc?export=view&id={file_id}"

        logger.info(f"GDRIVE_UTIL: File '{drive_file_name}' uploaded. ID: {file_id}, Link: {direct_link}")
        return file_id, direct_link
    except Exception as e:
        logger.error(f"GDRIVE_UTIL: Error uploading file '{drive_file_name}': {e}", exc_info=True)
        return None, None


# delete_from_drive funksiyasiga ham shunga o'xshash loglar qo'shish mumkin
def delete_from_drive(file_id: str):
    try:
        if not file_id:
            logger.warning("GDRIVE_UTIL: No file ID provided for deletion.")
            return False
        logger.info(f"GDRIVE_UTIL: Attempting to delete GDrive file ID: {file_id}")
        drive = _get_drive_service()
        drive_file = drive.CreateFile({'id': file_id})
        drive_file.Delete()
        logger.info(f"GDRIVE_UTIL: File with ID {file_id} successfully deleted from GDrive.")
        return True
    except Exception as e:
        logger.error(f"GDRIVE_UTIL: Error deleting file with ID {file_id} from GDrive: {e}", exc_info=True)
        return False
