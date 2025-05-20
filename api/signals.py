from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings
import os
import logging
from .models import Product, Category, Promotion  # Rasmli modellar
from .gdrive_utils import upload_to_drive, delete_from_drive

logger = logging.getLogger(__name__)


def handle_gdrive_upload(instance, image_field_name='image'):
    if not hasattr(instance, image_field_name): return

    image_file = getattr(instance, image_field_name)
    gdrive_id_field_name = 'google_drive_file_id'
    gdrive_url_field_name = 'image_gdrive_url'

    old_gdrive_id = getattr(instance, gdrive_id_field_name, None)

    if image_file and hasattr(image_file, 'path'):  # Agar yangi/o'zgargan rasm bo'lsa
        try:
            if old_gdrive_id:
                logger.info(
                    f"Attempting to delete old GDrive file {old_gdrive_id} for {instance._meta.model_name} {instance.pk}")
                delete_from_drive(old_gdrive_id)
                setattr(instance, gdrive_id_field_name, None)
                setattr(instance, gdrive_url_field_name, None)

            file_path = image_file.path
            # Google Drive uchun unikal nom yaratamiz
            base_name, ext = os.path.splitext(os.path.basename(file_path))
            drive_file_name = f"{instance._meta.model_name}_{instance.pk}_{base_name}{ext}"

            # Google Drive papka ID sini settings dan olish (ixtiyoriy)
            drive_folder_id = getattr(settings, 'GOOGLE_DRIVE_UPLOAD_FOLDER_ID', None)
            drive_folder_id = None  # Hozircha rootga yuklaymiz

            file_id, file_url = upload_to_drive(file_path, drive_file_name, drive_folder_id)

            if file_id and file_url:
                # Signalni vaqtincha o'chirib, modelni yangilaymiz
                # Bu cheksiz save() chaqiruvini oldini oladi
                sender_model = instance.__class__
                post_save.disconnect(process_gdrive_for_product, sender=sender_model)
                post_save.disconnect(process_gdrive_for_category, sender=sender_model)
                post_save.disconnect(process_gdrive_for_promotion, sender=sender_model)

                setattr(instance, gdrive_id_field_name, file_id)
                setattr(instance, gdrive_url_field_name, file_url)
                instance.save(update_fields=[gdrive_id_field_name, gdrive_url_field_name])

                post_save.connect(process_gdrive_for_product, sender=Product)
                post_save.connect(process_gdrive_for_category, sender=Category)
                post_save.connect(process_gdrive_for_promotion, sender=Promotion)

                logger.info(f"{instance._meta.model_name} {instance.pk} image uploaded to GDrive: {file_id}")

                # Lokal faylni o'chirish (agar serverda joy tejamoqchi bo'lsak)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        instance.image = None  # Agar lokal faylni butunlay o'chirib, faqat GDrive linkini qoldirsak
                        instance.save(update_fields=['image'])
                        logger.info(f"Local file {file_path} deleted for {instance._meta.model_name} {instance.pk}")
                    except Exception as e_rem:
                        logger.error(f"Could not remove local file {file_path}: {e_rem}")
            else:
                logger.error(
                    f"Failed to get file_id or file_url from GDrive for {instance._meta.model_name} {instance.pk}")

        except FileNotFoundError:
            logger.warning(
                f"Local image file not found for {instance._meta.model_name} {instance.pk} at {getattr(image_file, 'path', 'N/A')}. Skipping GDrive upload.")
        except Exception as e:
            logger.error(f"General error in handle_gdrive_upload for {instance._meta.model_name} {instance.pk}: {e}",
                         exc_info=True)

    elif not image_file and old_gdrive_id:  # Rasm olib tashlandi
        try:
            logger.info(
                f"Image removed for {instance._meta.model_name} {instance.pk}. Deleting GDrive file {old_gdrive_id}")
            delete_from_drive(old_gdrive_id)

            sender_model = instance.__class__
            post_save.disconnect(process_gdrive_for_product, sender=sender_model)
            post_save.disconnect(process_gdrive_for_category, sender=sender_model)
            post_save.disconnect(process_gdrive_for_promotion, sender=sender_model)

            setattr(instance, gdrive_id_field_name, None)
            setattr(instance, gdrive_url_field_name, None)
            instance.save(update_fields=[gdrive_id_field_name, gdrive_url_field_name])

            post_save.connect(process_gdrive_for_product, sender=Product)
            post_save.connect(process_gdrive_for_category, sender=Category)
            post_save.connect(process_gdrive_for_promotion, sender=Promotion)
        except Exception as e:
            logger.error(
                f"Error deleting GDrive file for {instance._meta.model_name} {instance.pk} after image removal: {e}",
                exc_info=True)


# Har bir model uchun alohida signal receiver yoki bitta umumiy (model tekshiruvi bilan)
@receiver(post_save, sender=Product)
def process_gdrive_for_product(sender, instance, created, **kwargs):
    update_fields = kwargs.get('update_fields')
    if kwargs.get('raw', False): return  # Raw import paytida ishlamasin

    process_upload = False
    if created and instance.image:  # Yangi obyekt va rasm bor
        process_upload = True
    elif not created and instance.image:  # Mavjud obyekt va rasm bor (o'zgargan yoki yo'qligini bilmaymiz)
        if update_fields is None or 'image' in update_fields:
            process_upload = True
    elif not created and not instance.image and instance.google_drive_file_id:  # Rasm o'chirildi
        process_upload = True  # Bu handle_gdrive_upload ichida o'chirishni trigger qiladi

    if process_upload:
        logger.info(f"Post_save signal for Product {instance.pk}, image changed or new. Processing GDrive.")
        handle_gdrive_upload(instance, image_field_name='image')
    # else:
    # logger.debug(f"Post_save signal for Product {instance.pk}, image not changed. Skipping GDrive.")


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
