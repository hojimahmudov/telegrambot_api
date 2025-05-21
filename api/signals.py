# api/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
import os
import logging

from .models import Product, Category, Promotion
from .gdrive_utils import upload_to_drive, delete_from_drive

logger = logging.getLogger(__name__)


def handle_gdrive_upload(instance, image_field_name='image'):  # image_field_name bu modeldagi ImageField nomi
    model_name = instance._meta.model_name
    instance_pk = getattr(instance, 'pk', 'UnknownPK')
    log_prefix = f"GDrive Sync ({model_name} PK:{instance_pk}):"

    if not hasattr(instance, image_field_name):
        logger.warning(f"{log_prefix} Instance has no field '{image_field_name}'. Skipping.")
        return

    current_field_file_obj = getattr(instance, image_field_name, None)  # Bu Django FieldFile obyekti

    # Google Drive bilan bog'liq maydon nomlari
    gdrive_id_db_field = 'google_drive_file_id'  # Modelda shu nom bilan
    gdrive_url_db_field = 'image_gdrive_url'  # Modelda shu nom bilan

    # Saqlashdan oldingi GDrive ID sini olish
    old_gdrive_id_from_db = None
    if instance.pk and not instance._state.adding:
        try:
            db_instance = instance.__class__.objects.get(pk=instance.pk)
            old_gdrive_id_from_db = getattr(db_instance, gdrive_id_db_field, None)
        except instance.__class__.DoesNotExist:
            logger.warning(f"{log_prefix} Could not fetch DB instance for PK {instance.pk} to get old GDrive ID.")

    # Modelning __init__ da o'rnatilgan _original_image_name ga tayanamiz
    original_image_name_at_init = getattr(instance, '_original_image_name', None)
    current_image_name_in_field = current_field_file_obj.name if current_field_file_obj else None

    image_content_has_genuinely_changed = current_image_name_in_field != original_image_name_at_init

    logger.info(
        f"{log_prefix} Called. Current image name: '{current_image_name_in_field}', "
        f"Original image name (from init): '{original_image_name_at_init}', "
        f"Image content changed flag: {image_content_has_genuinely_changed}"
    )

    if not image_content_has_genuinely_changed:
        logger.info(
            f"{log_prefix} Image field content not considered changed based on initial name. Skipping GDrive operations.")
        return

    # Agar rasm o'zgargan bo'lsa (yangi, boshqa yoki o'chirilgan)

    new_gdrive_id_value = None
    new_gdrive_url_value = None
    path_of_locally_saved_file_for_upload = None  # Agar yangi fayl GDrive ga yuklansa, uning lokal yo'lini saqlaymiz

    # 1. Agar eski GDrive fayl mavjud bo'lsa va rasm o'zgargan yoki o'chirilgan bo'lsa, uni Drive'dan o'chiramiz
    if old_gdrive_id_from_db:
        logger.info(f"{log_prefix} Attempting to delete old GDrive file: {old_gdrive_id_from_db}")
        delete_from_drive(old_gdrive_id_from_db)
        # DB maydonlarini ham None qilamiz, agar yangi rasm yuklanmasa shunday qoladi
        new_gdrive_id_value = None
        new_gdrive_url_value = None

    # 2. Agar yangi rasm fayli mavjud bo'lsa (ya'ni, rasm maydoni bo'shatilmagan)
    if current_field_file_obj and hasattr(current_field_file_obj, 'path') and \
            current_field_file_obj.path and os.path.exists(current_field_file_obj.path):

        local_path = current_field_file_obj.path
        logger.info(f"{log_prefix} New/changed image found at '{local_path}'. Processing GDrive upload.")

        try:
            base_name, ext = os.path.splitext(os.path.basename(local_path))
            drive_file_name = f"{model_name}_{instance.pk if instance.pk else 'temp_new'}_{base_name}{ext}"

            temp_id, temp_url = upload_to_drive(local_path, drive_file_name)  # drive_folder_id None

            if temp_id and temp_url:
                new_gdrive_id_value = temp_id
                new_gdrive_url_value = temp_url
                path_of_locally_saved_file_for_upload = local_path  # Muvaffaqiyatli yuklashdan keyin o'chirish uchun
                logger.info(f"{log_prefix} Image uploaded to GDrive. New ID: {new_gdrive_id_value}")
            else:
                logger.error(
                    f"{log_prefix} GDrive upload failed for local file {local_path}. GDrive fields will remain/become None.")
                # new_gdrive_id_value va new_gdrive_url_value None bo'lib qoladi
        except Exception as e:
            logger.error(f"{log_prefix} Error during GDrive upload process for {local_path}: {e}", exc_info=True)
            new_gdrive_id_value = None
            new_gdrive_url_value = None

    # else: Rasm maydoni bo'shatilgan (current_field_file_obj yo'q)
    # Bu holatda old_gdrive_id_from_db (agar bo'lsa) yuqorida o'chirilgan va
    # new_gdrive_id_value/new_gdrive_url_value None bo'lib qoladi. Bu to'g'ri.

    # Model obyektidagi GDrive maydonlarini va lokal rasm maydonini yangilash kerakmi?
    fields_to_update_in_db = []

    if getattr(instance, gdrive_id_db_field) != new_gdrive_id_value:
        setattr(instance, gdrive_id_db_field, new_gdrive_id_value)
        fields_to_update_in_db.append(gdrive_id_db_field)

    if getattr(instance, gdrive_url_db_field) != new_gdrive_url_value:
        setattr(instance, gdrive_url_db_field, new_gdrive_url_value)
        fields_to_update_in_db.append(gdrive_url_db_field)

    # Agar yangi rasm GDrive'ga muvaffaqiyatli yuklangan bo'lsa, LOKAL ImageFieldni tozalaymiz
    if path_of_locally_saved_file_for_upload:  # Bu faqat GDrive'ga muvaffaqiyatli yuklanganda o'rnatiladi
        if getattr(instance, image_field_name) is not None:
            setattr(instance, image_field_name, None)  # Django ImageFieldni None qilamiz
            fields_to_update_in_db.append(image_field_name)
    # Agar rasm admin panelidan "Clear" qilingan bo'lsa, Django o'zi instance.image ni None qiladi.
    # Biz faqat GDrive ID/URL ni None qilishimiz kerak (yuqorida qilingan).
    # Lekin baribir image_field_name ni update_fields ga qo'shishimiz mumkin, to'g'ri saqlanishi uchun.
    elif image_content_has_genuinely_changed and not current_field_file_obj:  # Rasm olib tashlangan
        if image_field_name not in fields_to_update_in_db and getattr(instance, image_field_name) is not None:
            # Bu holat Django admin "clear" checkbox'i bosilganda yuz beradi
            # Django o'zi instance.image ni None qiladi, biz shunchaki update_fields ga qo'shamiz
            fields_to_update_in_db.append(image_field_name)

    if fields_to_update_in_db:
        logger.info(f"{log_prefix} Saving updated GDrive/Image fields to DB: {fields_to_update_in_db}")

        sender_model = instance.__class__
        receiver_func_name = f'process_gdrive_for_{model_name.lower()}'
        receiver_func = globals().get(receiver_func_name)

        if receiver_func: post_save.disconnect(receiver_func, sender=sender_model)
        try:
            instance.save(update_fields=list(set(fields_to_update_in_db)))  # unique fields
        except Exception as db_save_e:
            logger.error(f"{log_prefix} Failed to save GDrive related fields to DB: {db_save_e}", exc_info=True)
        if receiver_func: post_save.connect(receiver_func, sender=sender_model)
    else:
        logger.info(f"{log_prefix} No changes to GDrive/Image fields in DB needed for this signal instance.")

    # DBga yozilgandan keyin lokal faylni o'chiramiz (agar yuklangan bo'lsa)
    if path_of_locally_saved_file_for_upload and os.path.exists(path_of_locally_saved_file_for_upload):
        try:
            os.remove(path_of_locally_saved_file_for_upload)
            logger.info(f"{log_prefix} Successfully deleted local temp file: {path_of_locally_saved_file_for_upload}")
        except OSError as e_del_local:
            logger.error(
                f"{log_prefix} Failed to delete local temp file {path_of_locally_saved_file_for_upload}: {e_del_local}",
                exc_info=True)


# --- Product uchun signallar ---
@receiver(post_save, sender=Product)
def process_gdrive_for_product(sender, instance, created, **kwargs):
    # Agar faqat GDrive maydonlari o'zgarayotgan bo'lsa (handle_gdrive_upload ichidan)
    if kwargs.get('update_fields') and all(
            f in ['google_drive_file_id', 'image_gdrive_url'] for f in kwargs['update_fields']):
        return
    if kwargs.get('raw', False): return  # Fixture yuklanayotganda ishlamasin

    logger.info(f"Product post_save signal triggered for PK: {instance.pk}, Created: {created}")
    handle_gdrive_upload(instance, 'image')


@receiver(post_delete, sender=Product)
def delete_product_image_from_drive(sender, instance, **kwargs):
    logger.info(f"Product post_delete signal triggered for PK: {instance.pk}")
    if instance.google_drive_file_id:
        delete_from_drive(instance.google_drive_file_id)


# --- Category uchun signallar ---
@receiver(post_save, sender=Category)
def process_gdrive_for_category(sender, instance, created, **kwargs):
    if kwargs.get('update_fields') and all(
            f in ['google_drive_file_id', 'image_gdrive_url'] for f in kwargs['update_fields']):
        return
    if kwargs.get('raw', False): return
    logger.info(f"Category post_save signal triggered for PK: {instance.pk}, Created: {created}")
    handle_gdrive_upload(instance, 'image')


@receiver(post_delete, sender=Category)
def delete_category_image_from_drive(sender, instance, **kwargs):
    logger.info(f"Category post_delete signal triggered for PK: {instance.pk}")
    if instance.google_drive_file_id:
        delete_from_drive(instance.google_drive_file_id)


# --- Promotion uchun signallar ---
@receiver(post_save, sender=Promotion)
def process_gdrive_for_promotion(sender, instance, created, **kwargs):
    if kwargs.get('update_fields') and all(
            f in ['google_drive_file_id', 'image_gdrive_url'] for f in kwargs['update_fields']):
        return
    if kwargs.get('raw', False): return
    logger.info(f"Promotion post_save signal triggered for PK: {instance.pk}, Created: {created}")
    handle_gdrive_upload(instance, 'image')


@receiver(post_delete, sender=Promotion)
def delete_promotion_image_from_drive(sender, instance, **kwargs):
    logger.info(f"Promotion post_delete signal triggered for PK: {instance.pk}")
    if instance.google_drive_file_id:
        delete_from_drive(instance.google_drive_file_id)
