# api/serializers.py

from rest_framework import serializers
from parler_rest.serializers import TranslatableModelSerializer
from parler_rest.fields import TranslatedFieldsField  # Til tablari uchun (ixtiyoriy)
from .models import User, Category, Product


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
