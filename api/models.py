# api/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from parler.models import TranslatableModel, TranslatedFields


# --- Foydalanuvchi Modeli ---
class User(AbstractUser):
    """
    Django'ning standart User modelini Telegram ID va telefon raqami
    bilan kengaytiradigan maxsus foydalanuvchi modeli.
    """
    # Standart username, first_name, last_name, email, is_staff, is_active, date_joined AbstractUser'dan keladi.
    # Biz qo'shimcha maydonlarni qo'shamiz:

    telegram_id = models.BigIntegerField(
        _("Telegram ID"),
        unique=True,
        help_text=_("Foydalanuvchining noyob Telegram identifikatori")
    )
    phone_number = models.CharField(
        _("Telefon raqami"),
        max_length=20,
        unique=True,
        help_text=_("Foydalanuvchining telefon raqami (xalqaro formatda, masalan, +998901234567)")
    )
    # Email maydonini majburiy bo'lmagan holga keltiramiz
    email = models.EmailField(_('email address'), blank=True, null=True)

    # Login uchun username o'rniga boshqa maydon ishlatmoqchi bo'lsak
    # USERNAME_FIELD = 'phone_number' # Buni o'zgartirsak, UserManager'ni ham moslash kerak bo'ladi
    # Hozircha 'username' qolaversin.

    # createsuperuser orqali admin yaratganda so'raladigan qo'shimcha majburiy maydonlar
    REQUIRED_FIELDS = ['telegram_id', 'phone_number', 'first_name']

    class Meta:
        verbose_name = _("Foydalanuvchi")
        verbose_name_plural = _("Foydalanuvchilar")
        ordering = ['-date_joined']  # Ro'yxatdan o'tgan sanasi bo'yicha teskari tartib

    def __str__(self):
        return self.username or self.phone_number or f"User {self.pk}"


# --- Kategoriya Modeli ---
class Category(TranslatableModel):  # <-- TranslatableModel'dan meros olamiz
    """Mahsulot kategoriyalari uchun model (ko'p tilli)."""
    translations = TranslatedFields(  # <-- Tarjima qilinadigan maydonlar shu yerda
        name=models.CharField(
            _("Nomi"),
            max_length=100,
            # Endi unique=True shu yerda emas, Meta'da bo'lishi mumkin yoki shart emas
        )
    )
    # Tarjima qilinmaydigan maydonlar shu yerda qoladi
    image_url = models.URLField(
        _("Rasm manzili"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Kategoriya rasmining URL manzili (ixtiyoriy)")
    )
    is_active = models.BooleanField(
        _("Aktiv"),
        default=True,
        help_text=_("Kategoriya mijozlar uchun ko'rinadimi?")
    )
    order = models.PositiveIntegerField(
        _("Tartib raqami"),
        default=0,
        help_text=_("Kategoriyalarni saralash uchun raqam (kichigi birinchi)")
    )

    class Meta:
        verbose_name = _("Kategoriya")
        verbose_name_plural = _("Kategoriyalar")
        ordering = ['order']  # Nomi endi translations'da bo'lgani uchun order bo'yicha saralaymiz

    def __str__(self):
        # safe_translation_getter - agar tarjima bo'lmasa xato bermaydi
        return self.safe_translation_getter('name', any_language=True) or f"Category {self.pk}"


# --- Mahsulot Modeli ---
class Product(TranslatableModel):
    translations = TranslatedFields(
        name=models.CharField(
            _("Nomi"),
            max_length=150
        ),
        description=models.TextField(
            _("Tavsifi"),
            null=True,
            blank=True
        )
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='products',
        verbose_name=_("Kategoriya")
    )
    price = models.DecimalField(
        _("Narxi"),
        max_digits=10,
        decimal_places=2
    )
    image_url = models.URLField(
        _("Rasm manzili"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Mahsulot rasmining URL manzili (ixtiyoriy)")
    )
    is_available = models.BooleanField(
        _("Mavjud"),
        default=True,
        help_text=_("Mahsulot hozirda buyurtma uchun mavjudmi?")
    )
    created_at = models.DateTimeField(
        _("Yaratilgan vaqti"),
        auto_now_add=True
    )
    updated_at = models.DateTimeField(
        _("Yangilangan vaqti"),
        auto_now=True
    )

    class Meta:
        verbose_name = _("Mahsulot")
        verbose_name_plural = _("Mahsulotlar")
        ordering = ['pk']  # Eng oddiy tartiblash

    def __str__(self):
        return self.safe_translation_getter('name', any_language=True) or f"Product {self.pk}"
