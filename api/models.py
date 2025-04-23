# api/models.py
from django.db import models
from django.conf import settings  # User modelini olish uchun qulay usul
from django.core.validators import MinValueValidator  # Minimal qiymatni tekshirish uchun
from django.db.models import UniqueConstraint  # Unikalikni ta'minlash uchun
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _
from parler.models import TranslatableModel, TranslatedFields
from django.utils import timezone


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

    otp_code = models.CharField(
        _("OTP Kodu"),
        max_length=6,
        null=True,
        blank=True  # Kod tasdiqlangandan keyin bo'shatilishi mumkin
    )
    otp_created_at = models.DateTimeField(
        _("OTP Yaratilgan Vaqti"),
        null=True,
        blank=True
    )
    # --- is_active maydonining standart qiymatini o'zgartiramiz ---
    is_active = models.BooleanField(
        _('active'),
        default=False,  # <-- Foydalanuvchi OTP tasdiqlamaguncha aktiv bo'lmaydi
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )

    REQUIRED_FIELDS = ['telegram_id', 'phone_number', 'first_name']

    class Meta:
        verbose_name = _("Foydalanuvchi")
        verbose_name_plural = _("Foydalanuvchilar")
        ordering = ['-date_joined']

    def __str__(self):
        return self.username or self.phone_number or f"User {self.pk}"

    def is_otp_valid(self, code):
        """OTP kod to'g'riligini va muddati o'tmaganligini tekshiradi."""
        if not self.otp_code or not self.otp_created_at:
            return False
        # Masalan, OTP 5 daqiqa amal qilsin
        if self.otp_created_at < timezone.now() - timezone.timedelta(minutes=5):
            return False
        return self.otp_code == code

    def clear_otp(self):
        """OTP kodni tozalaydi."""
        self.otp_code = None
        self.otp_created_at = None
        self.save(update_fields=['otp_code', 'otp_created_at'])


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


class Cart(models.Model):
    """Foydalanuvchining savatchasi."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,  # Sozlamalardan User modelini oladi
        on_delete=models.CASCADE,  # Foydalanuvchi o'chsa, savat ham o'chadi
        related_name='cart',  # User obyektidan savatga murojaat (user.cart)
        verbose_name=_("Foydalanuvchi")
    )
    created_at = models.DateTimeField(_("Yaratilgan vaqti"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Yangilangan vaqti"), auto_now=True)

    @property
    def total_price(self):
        """Savatdagi barcha mahsulotlarning umumiy narxini hisoblaydi."""
        return sum(item.get_item_total for item in self.items.all())

    class Meta:
        verbose_name = _("Savat")
        verbose_name_plural = _("Savatlar")

    def __str__(self):
        return f"{self.user.username} uchun savat"


class CartItem(models.Model):
    """Savatdagi bitta mahsulot qatori."""
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,  # Savat o'chsa, uning item'lari ham o'chadi
        related_name='items',  # Cart obyektidan item'larga murojaat (cart.items.all())
        verbose_name=_("Savat")
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,  # Mahsulot o'chsa, savatdan ham o'chadi (yoki SET_NULL/PROTECT)
        verbose_name=_("Mahsulot")
    )
    quantity = models.PositiveIntegerField(
        _("Soni"),
        default=1,
        validators=[MinValueValidator(1)]  # Miqdor kamida 1 bo'lishi kerak
    )
    added_at = models.DateTimeField(_("Qo'shilgan vaqti"), auto_now_add=True, null=True, blank=True)  # Optional

    @property
    def get_item_total(self):
        """Shu qatordagi mahsulot(lar)ning umumiy narxini hisoblaydi."""
        return self.product.price * self.quantity

    class Meta:
        verbose_name = _("Savat mahsuloti")
        verbose_name_plural = _("Savat mahsulotlari")
        # Bitta savatda bitta mahsulot faqat bir marta uchrashi kerakligini ta'minlaydi
        constraints = [
            UniqueConstraint(fields=['cart', 'product'], name='unique_cart_product')
        ]
        ordering = ['-added_at']  # Oxirgi qo'shilganlar birinchi (ixtiyoriy)

    def __str__(self):
        return f"{self.quantity} x {self.product.name} ({self.cart.user.username})"

class Order(models.Model):
    """Mijozlar tomonidan qilingan buyurtmalar."""
    STATUS_CHOICES = (
        ('new', _('Yangi')),
        ('preparing', _('Tayyorlanmoqda')),
        ('on_the_way', _('Yo\'lda')),
        ('delivered', _('Yetkazildi')),
        ('cancelled', _('Bekor qilindi')),
    )
    DELIVERY_CHOICES = (
        ('delivery', _('Yetkazib berish')),
        ('pickup', _('Olib ketish')),
    )
    PAYMENT_CHOICES = (
        ('cash', _('Naqd pul')),
        ('card', _('Karta orqali')), # Yoki 'payme', 'click'
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='orders', verbose_name=_("Foydalanuvchi")) # Agar user o'chsa, buyurtma qolsin
    status = models.CharField(_("Holati"), max_length=20, choices=STATUS_CHOICES, default='new', db_index=True) # Holat bo'yicha indekslash
    total_price = models.DecimalField(_("Umumiy summa"), max_digits=12, decimal_places=2)
    delivery_type = models.CharField(_("Yetkazib berish turi"), max_length=10, choices=DELIVERY_CHOICES, default='delivery')
    # Yetkazib berish uchun ma'lumotlar (agar delivery_type == 'delivery')
    address = models.TextField(_("Manzil"), null=True, blank=True)
    latitude = models.FloatField(_("Kenglik"), null=True, blank=True)
    longitude = models.FloatField(_("Uzunlik"), null=True, blank=True)
    # To'lov turi
    payment_type = models.CharField(_("To'lov turi"), max_length=10, choices=PAYMENT_CHOICES, default='cash')
    # Qo'shimcha izohlar
    notes = models.TextField(_("Izohlar"), null=True, blank=True)

    created_at = models.DateTimeField(_("Yaratilgan vaqti"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Yangilangan vaqti"), auto_now=True)

    class Meta:
        verbose_name = _("Buyurtma")
        verbose_name_plural = _("Buyurtmalar")
        ordering = ['-created_at'] # Oxirgi buyurtmalar birinchi

    def __str__(self):
        # Foydalanuvchi None bo'lishi mumkinligini hisobga olamiz (SET_NULL tufayli)
        user_display = self.user.username if self.user else (self.user.phone_number if self.user else _('Noma\'lum'))
        return f"Buyurtma #{self.pk} ({user_display}) - {self.get_status_display()}"


class OrderItem(models.Model):
    """Buyurtmadagi alohida mahsulot qatori."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items', verbose_name=_("Buyurtma"))
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, verbose_name=_("Mahsulot")) # Mahsulot o'chsa ham buyurtmada qolsin
    quantity = models.PositiveIntegerField(_("Soni"), default=1, validators=[MinValueValidator(1)])
    # Muhim: Mahsulot narxini buyurtma paytida saqlab qolamiz!
    price_per_unit = models.DecimalField(_("Birlik narxi (buyurtma paytida)"), max_digits=10, decimal_places=2)
    total_price = models.DecimalField(_("Umumiy narx"), max_digits=12, decimal_places=2) # quantity * price_per_unit

    class Meta:
        verbose_name = _("Buyurtma mahsuloti")
        verbose_name_plural = _("Buyurtma mahsulotlari")

    def save(self, *args, **kwargs):
        # total_price ni avtomatik hisoblaymiz (agar qo'lda kiritilmagan bo'lsa)
        # Yoki View'da hisoblab yozish ham mumkin. Bu yerda hisoblash qulayroq.
        self.total_price = self.price_per_unit * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        # Mahsulot None bo'lishi mumkinligini hisobga olamiz (SET_NULL tufayli)
        product_name = self.product.safe_translation_getter('name', any_language=True) if self.product else _("O'chirilgan mahsulot")
        return f"{self.quantity} x {product_name} (Buyurtma #{self.order.pk})"