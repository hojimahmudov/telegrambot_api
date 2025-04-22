# api/serializers.py

from rest_framework import serializers
from parler_rest.serializers import TranslatableModelSerializer
from parler_rest.fields import TranslatedFieldsField  # Til tablari uchun (ixtiyoriy)
from .models import User, Category, Product
import re


# --- User Serializer ---
class UserSerializer(serializers.ModelSerializer):
    """Foydalanuvchi ma'lumotlarini API uchun tayyorlaydi."""

    class Meta:
        model = User
        # API'da ko'rinadigan maydonlar
        fields = ['id', 'telegram_id', 'phone_number', 'username', 'first_name', 'last_name']
        # Ba'zi maydonlarni faqat o'qish uchun qilish mumkin (masalan, API orqali telegram_id'ni o'zgartirib bo'lmaydi)
        read_only_fields = ['telegram_id']


# --- Category Serializer ---
class CategorySerializer(TranslatableModelSerializer):
    """Kategoriya ma'lumotlarini (tarjimalari bilan) API uchun tayyorlaydi."""

    # DRF ning browsable API'sida tillar uchun alohida tablar chiqarish uchun:
    # translations = TranslatedFieldsField(shared_model=Category)

    class Meta:
        model = Category
        # API'da ko'rinadigan maydonlar
        fields = ['id', 'name', 'image_url', 'is_active', 'order']
        # 'name' maydoni avtomatik tarzda so'rov tiliga mos tarjimani qaytaradi


# --- Product Serializer ---
class ProductSerializer(TranslatableModelSerializer):
    """Mahsulot ma'lumotlarini (tarjimalari va kategoriyasi bilan) API uchun tayyorlaydi."""

    # Mahsulot ro'yxatida/detallarida kategoriya ma'lumotlarini ko'rsatish uchun
    # CategorySerializer'ni shu yerda ishlatamiz (faqat o'qish uchun)
    # Muhim: CategorySerializer ushbu ProductSerializer'dan oldinroq aniqlangan bo'lishi kerak
    category = CategorySerializer(read_only=True)

    # Mahsulot yaratish/yangilash paytida kategoriyani ID orqali belgilash uchun
    # Bu maydon faqat yozish uchun ishlatiladi (API'ga POST/PUT qilganda)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),  # Qaysi modeldan tanlash kerakligi
        source='category',  # Qaysi model maydoniga bog'lanishi
        write_only=True  # Faqat yozish uchun (GET so'rovida ko'rinmaydi)
    )

    # DRF ning browsable API'sida tillar uchun alohida tablar chiqarish uchun:
    # translations = TranslatedFieldsField(shared_model=Product)

    class Meta:
        model = Product
        # API'da ko'rinadigan maydonlar
        fields = [
            'id',
            'category',  # Ichki joylashgan Category obyekti (faqat o'qish uchun)
            'category_id',  # Kategoriya ID sini yozish uchun maydon
            'name',  # Tarjima qilinadigan maydon
            'description',  # Tarjima qilinadigan maydon
            'price',
            'image_url',
            'is_available'  # Mahsulot mavjudligi
        ]
        # 'name' va 'description' maydonlari avtomatik tarzda so'rov tiliga mos tarjimani qaytaradi


# --- Ro'yxatdan o'tish uchun Serializer ---
class RegistrationSerializer(serializers.Serializer):
    """Ro'yxatdan o'tish uchun kiruvchi ma'lumotlarni tekshiradi."""
    telegram_id = serializers.IntegerField(required=True)
    phone_number = serializers.CharField(required=True, max_length=20)
    first_name = serializers.CharField(required=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    username = serializers.CharField(required=False, allow_blank=True, max_length=150)

    def validate_phone_number(self, value):
        """Telefon raqami formatini tekshirish (soddalashtirilgan misol)."""
        # Masalan, +998 bilan boshlanib, jami 13 ta raqamdan iborat bo'lsin
        if not re.match(r'^\+998\d{9}$', value):
            raise serializers.ValidationError("Telefon raqami +998XXXXXXXXX formatida bo'lishi kerak.")
        return value

    # Agar username ham unique bo'lishi kerak bo'lsa, validate qo'shish mumkin
    def validate_username(self, value):
        if value and User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Bu username allaqachon mavjud.")
        return value


# --- OTP Tasdiqlash uchun Serializer ---
class OTPVerificationSerializer(serializers.Serializer):
    """OTP kodni tasdiqlash uchun kiruvchi ma'lumotlarni tekshiradi."""
    phone_number = serializers.CharField(required=True, max_length=20)
    otp_code = serializers.CharField(required=True, min_length=4, max_length=6)  # OTP uzunligiga moslang

    def validate_phone_number(self, value):
        """Telefon raqami formatini tekshirish."""
        if not re.match(r'^\+998\d{9}$', value):
            raise serializers.ValidationError("Telefon raqami +998XXXXXXXXX formatida bo'lishi kerak.")
        return value

    def validate_otp_code(self, value):
        """OTP kod faqat raqamlardan iboratligini tekshirish."""
        if not value.isdigit():
            raise serializers.ValidationError("OTP kod faqat raqamlardan iborat bo'lishi kerak.")
        return value
