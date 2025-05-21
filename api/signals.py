from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
import os
import logging
from .models import Product, Category, Promotion  # Rasmli modellar
from .gdrive_utils import upload_to_drive, delete_from_drive

logger = logging.getLogger(__name__)  # Har bir faylda logger olishni unutmang


def handle_gdrive_upload(instance, image_field_name='image'):
    logger.info(f"HANDLE_GDRIVE: Called for {instance._meta.model_name} {instance.pk}")
    if not hasattr(instance, image_field_name):
        logger.warning(f"HANDLE_GDRIVE: Instance has no field '{image_field_name}'. Skipping.")
        return

    image_file = getattr(instance, image_field_name)
    gdrive_id_field_name = 'google_drive_file_id'
    gdrive_url_field_name = 'image_gdrive_url'
    old_gdrive_id = getattr(instance, gdrive_id_field_name, None)

    logger.info(
        f"HANDLE_GDRIVE: Current image_file: {image_file.name if image_file else 'None'}. Old GDrive ID: {old_gdrive_id}")

    if image_file and hasattr(image_file, 'path') and image_file.path:
        logger.info(f"HANDLE_GDRIVE: New/changed image found: {image_file.path}")
        try:
            if old_gdrive_id:
                logger.info(f"HANDLE_GDRIVE: Attempting to delete old GDrive file {old_gdrive_id}")
                delete_from_drive(old_gdrive_id)  # Bu gdrive_utils dan

            file_path = image_file.path
            base_name, ext = os.path.splitext(os.path.basename(file_path))
            drive_file_name = f"{instance._meta.model_name}_{instance.pk}_{base_name}{ext}"
            drive_folder_id = None  # Hozircha rootga

            logger.info(f"HANDLE_GDRIVE: Calling upload_to_drive with path: {file_path}, name: {drive_file_name}")
            file_id, file_url = upload_to_drive(file_path, drive_file_name, drive_folder_id)  # Bu gdrive_utils dan

            if file_id and file_url:
                logger.info(f"HANDLE_GDRIVE: Upload successful. GDrive ID: {file_id}, URL: {file_url}")

                # Rekursiyani oldini olish uchun signallarni vaqtincha o'chiramiz
                sender_model = instance.__class__
                post_save.disconnect(globals().get(f'process_gdrive_for_{sender_model._meta.model_name.lower()}'),
                                     sender=sender_model)

                setattr(instance, gdrive_id_field_name, file_id)
                setattr(instance, gdrive_url_field_name, file_url)
                instance.save(update_fields=[gdrive_id_field_name, gdrive_url_field_name])

                post_save.connect(globals().get(f'process_gdrive_for_{sender_model._meta.model_name.lower()}'),
                                  sender=sender_model)
                logger.info(f"HANDLE_GDRIVE: {instance._meta.model_name} {instance.pk} GDrive fields updated in DB.")
            else:
                logger.error(
                    f"HANDLE_GDRIVE: upload_to_drive returned None for {instance._meta.model_name} {instance.pk}")
        except FileNotFoundError:
            logger.warning(
                f"HANDLE_GDRIVE: Local image file not found for {instance._meta.model_name} {instance.pk}. Path: {getattr(image_file, 'path', 'N/A')}")
        except Exception as e:
            logger.error(
                f"HANDLE_GDRIVE: Error in GDrive upload logic for {instance._meta.model_name} {instance.pk}: {e}",
                exc_info=True)

    elif not image_file and old_gdrive_id:  # Rasm olib tashlandi
        logger.info(
            f"HANDLE_GDRIVE: Image removed for {instance._meta.model_name} {instance.pk}. Deleting GDrive file {old_gdrive_id}")
        try:
            delete_from_drive(old_gdrive_id)
            sender_model = instance.__class__
            post_save.disconnect(globals().get(f'process_gdrive_for_{sender_model._meta.model_name.lower()}'),
                                 sender=sender_model)
            setattr(instance, gdrive_id_field_name, None)
            setattr(instance, gdrive_url_field_name, None)
            instance.save(update_fields=[gdrive_id_field_name, gdrive_url_field_name])
            post_save.connect(globals().get(f'process_gdrive_for_{sender_model._meta.model_name.lower()}'),
                              sender=sender_model)
            logger.info(f"HANDLE_GDRIVE: GDrive fields cleared in DB for {instance._meta.model_name} {instance.pk}.")
        except Exception as e:
            logger.error(
                f"HANDLE_GDRIVE: Error deleting GDrive file for {instance._meta.model_name} {instance.pk} after image removal: {e}",
                exc_info=True)
    else:
        logger.info(
            f"HANDLE_GDRIVE: No new image and no old GDrive ID, or image unchanged. Skipping GDrive operations for {instance._meta.model_name} {instance.pk}.")


@receiver(post_save, sender=Product)
def process_gdrive_for_product(sender, instance, created, **kwargs):
    logger.critical(
        f"DEBUG_SIGNAL: process_gdrive_for_product FIRED for Product PK: {instance.pk}, Created: {created}, UpdateFields: {kwargs.get('update_fields')}")

    # Bu shartlarni vaqtincha olib turamiz yoki log qilamiz
    raw_save = kwargs.get('raw', False)
    update_fields = kwargs.get('update_fields')
    logger.info(f"DEBUG_SIGNAL: Raw save: {raw_save}")
    if update_fields:
        logger.info(f"DEBUG_SIGNAL: Update fields: {update_fields}")

    # if raw_save:
    #     logger.info("DEBUG_SIGNAL: Skipping GDrive due to raw save.")
    #     return

    # if update_fields and all(field in ['google_drive_file_id', 'image_gdrive_url'] for field in update_fields) and len(update_fields) <= 2:
    #     logger.info(f"DEBUG_SIGNAL: Skipping GDrive because only GDrive fields were updated.")
    #     return

    logger.info(f"DEBUG_SIGNAL: Proceeding to call handle_gdrive_upload for Product {instance.pk}")
    handle_gdrive_upload(instance, image_field_name='image')


@receiver(post_delete, sender=Product)
def delete_product_image_from_drive(sender, instance, **kwargs):
    if instance.google_drive_file_id:
        logger.info(
            f"Post_delete signal for Product {instance.pk}. Deleting GDrive file {instance.google_drive_file_id}")
        delete_from_drive(instance.google_drive_file_id)


# Category va Promotion uchun ham xuddi shunday process_gdrive_for_... va delete_..._image_from_drive signallarini yarating.
@receiver(post_save, sender=Category)
def process_gdrive_for_category(sender, instance, created, **kwargs):
    update_fields = kwargs.get('update_fields')
    if kwargs.get('raw', False): return
    process_upload = False
    if created and instance.image:
        process_upload = True
    elif not created and (update_fields is None or 'image' in update_fields):
        process_upload = True

    if process_upload:
        logger.info(f"Post_save signal for Category {instance.pk}, image changed or new. Processing GDrive.")
        handle_gdrive_upload(instance, image_field_name='image')


@receiver(post_delete, sender=Category)
def delete_category_image_from_drive(sender, instance, **kwargs):
    if instance.google_drive_file_id:
        logger.info(
            f"Post_delete signal for Category {instance.pk}. Deleting GDrive file {instance.google_drive_file_id}")
        delete_from_drive(instance.google_drive_file_id)


@receiver(post_save, sender=Promotion)
def process_gdrive_for_promotion(sender, instance, created, **kwargs):
    update_fields = kwargs.get('update_fields')
    if kwargs.get('raw', False): return
    process_upload = False
    if created and instance.image:
        process_upload = True
    elif not created and (update_fields is None or 'image' in update_fields):
        process_upload = True

    if process_upload:
        logger.info(f"Post_save signal for Promotion {instance.pk}, image changed or new. Processing GDrive.")
        handle_gdrive_upload(instance, image_field_name='image')


@receiver(post_delete, sender=Promotion)
def delete_promotion_image_from_drive(sender, instance, **kwargs):
    if instance.google_drive_file_id:
        logger.info(
            f"Post_delete signal for Promotion {instance.pk}. Deleting GDrive file {instance.google_drive_file_id}")
        delete_from_drive(instance.google_drive_file_id)
