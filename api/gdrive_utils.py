# api/gdrive_utils.py
import os
import logging
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from django.conf import settings

logger = logging.getLogger(__name__)


def _get_drive_service():
    """Google Drive servisini autentifikatsiya qilib qaytaradi."""
    gauth = GoogleAuth()
    gauth.settings['client_config_backend'] = 'service'
    gauth.settings['service_config'] = {
        "client_json_file_path": settings.GOOGLE_DRIVE_CREDENTIALS_JSON_PATH,
        "client_user_email": "chocoberry@chocoberryimage.iam.gserviceaccount.com"
    }
    logger.info("GDRIVE_UTIL: Authenticating GAuth service with service account...")
    gauth.ServiceAuth()
    logger.info("GDRIVE_UTIL: GAuth service authenticated. Creating GoogleDrive instance.")
    return GoogleDrive(gauth)


def upload_to_drive(local_file_path: str, drive_file_name: str, drive_folder_id: str = None) -> tuple[
    str | None, str | None]:
    try:
        if not os.path.exists(local_file_path):
            logger.error(f"GDrive Upload: File not found at path: {local_file_path}")
            return None, None

        drive = _get_drive_service()
        file_metadata = {'title': drive_file_name}
        if drive_folder_id:
            file_metadata['parents'] = [{'id': drive_folder_id}]

        drive_file = drive.CreateFile(file_metadata)
        drive_file.SetContentFile(local_file_path)
        drive_file.Upload()
        drive_file.InsertPermission({'type': 'anyone', 'value': 'anyone', 'role': 'reader'})

        file_id = drive_file['id']
        direct_link = f"https://drive.google.com/uc?export=view&id={file_id}"

        logger.info(f"GDrive Upload: File '{drive_file_name}' uploaded. ID: {file_id}")
        return file_id, direct_link
    except Exception as e:
        logger.error(f"GDrive Upload: Error uploading file '{drive_file_name}': {e}", exc_info=True)
        return None, None


def delete_from_drive(file_id: str):
    try:
        if not file_id:
            logger.warning("GDrive Delete: No file ID provided for deletion.")
            return False

        drive = _get_drive_service()
        drive_file = drive.CreateFile({'id': file_id})
        drive_file.Delete()
        logger.info(f"GDrive Delete: File with ID {file_id} successfully deleted.")
        return True
    except Exception as e:
        # Google API ba'zan fayl topilmasa ham xatolik bermasligi mumkin,
        # lekin fayl topilmagani uchun "Cannot retrieve B medlem..." kabi xatolar berishi mumkin.
        # Agar xato "File not found" yoki shunga o'xshash bo'lsa, warning qilsak yetarli.
        if hasattr(e, 'resp') and e.resp.status == 404:
            logger.warning(
                f"GDrive Delete: File with ID {file_id} not found on GDrive (already deleted or invalid ID).")
            return True  # Fayl yo'q bo'lsa, o'chirish muvaffaqiyatli deb hisoblaymiz
        logger.error(f"GDrive Delete: Error deleting file with ID {file_id}: {e}", exc_info=True)
        return False
