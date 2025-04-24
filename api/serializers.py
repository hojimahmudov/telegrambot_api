# api/serializers.py
import re
from rest_framework import serializers
from parler_rest.serializers import TranslatableModelSerializer
from parler_rest.fields import TranslatedFieldsField  # Til tablari uchun (ixtiyoriy)
from .models import (
    User, Category, Product, Cart, CartItem, Order, OrderItem,
    Branch, WorkingHours
)


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


class CartItemSerializer(serializers.ModelSerializer):
    """Savatdagi alohida mahsulot qatorini serializatsiya qiladi."""
    # Mahsulot ma'lumotlarini ko'rsatish uchun ProductSerializer'dan foydalanamiz
    # Bu read_only, chunki savatni ko'rsatganda mahsulotni o'zgartirmaymiz
    # ProductSerializer avvalroq aniqlangan bo'lishi kerak
    product = ProductSerializer(read_only=True)

    # Savatga mahsulot qo'shish/o'zgartirish uchun faqat ID ishlatiladi
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.all(),
        source='product',
        write_only=True  # Faqat yozish uchun
    )

    # Mahsulot soni (o'qish va yozish uchun)
    # quantity = serializers.IntegerField(min_value=1) # Modelda validator borligi uchun bu shart emas

    # Shu qatordagi umumiy narxni hisoblash uchun (faqat o'qish uchun)
    # Modelda 'get_item_total' property'si borligi uchun shuni ishlatamiz
    item_total = serializers.DecimalField(source='get_item_total', max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_id', 'quantity', 'item_total', 'added_at']
        read_only_fields = ['id', 'added_at']  # Bu maydonlar avtomatik to'ldiriladi


class CartSerializer(serializers.ModelSerializer):
    """To'liq savat ma'lumotlarini (mahsulotlari bilan) serializatsiya qiladi."""
    # Savatdagi mahsulotlar ro'yxati (ichma-ich joylashgan)
    # Yuqoridagi CartItemSerializer'dan foydalanamiz
    items = CartItemSerializer(many=True, read_only=True)  # Ko'plab item bo'lishi mumkin

    # Savatning umumiy summasi (faqat o'qish uchun)
    # Modelda 'total_price' property'si borligi uchun shuni ishlatamiz
    total_price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    # Foydalanuvchi ID si (ixtiyoriy, agar kerak bo'lsa)
    user_id = serializers.PrimaryKeyRelatedField(read_only=True, source='user.id')

    class Meta:
        model = Cart
        fields = ['id', 'user_id', 'items', 'total_price', 'updated_at']
        read_only_fields = ['id', 'updated_at']


class OrderItemSerializer(serializers.ModelSerializer):
    """Buyurtma tarkibidagi mahsulotni serializatsiya qiladi."""
    # Mahsulot ma'lumotlarini ProductSerializer orqali ko'rsatamiz
    # (Faqat o'qish uchun, chunki buyurtma yaratilgandan keyin o'zgarmaydi)
    # ProductSerializer avvalroq aniqlangan bo'lishi kerak
    product = ProductSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            'id',
            'product',
            'quantity',
            'price_per_unit',  # Buyurtma paytidagi narx
            'total_price'  # Shu qatorning umumiy summasi (quantity * price_per_unit)
        ]


class WorkingHoursSerializer(serializers.ModelSerializer):
    """Ish vaqtini serializatsiya qiladi."""
    # Haftaning kunini nomi bilan chiqarish uchun
    weekday_display = serializers.CharField(source='get_weekday_display', read_only=True)

    # Vaqtni HH:MM formatida chiqarish
    from_hour = serializers.TimeField(format='%H:%M')
    to_hour = serializers.TimeField(format='%H:%M')

    class Meta:
        model = WorkingHours
        fields = ['id', 'weekday', 'weekday_display', 'from_hour', 'to_hour']


class BranchSerializer(serializers.ModelSerializer):
    """Filial ma'lumotlarini (ish vaqtlari va ochiqlik statusi bilan) serializatsiya qiladi."""
    # Filialning ish vaqtlarini nested qilib chiqaramiz
    working_hours = WorkingHoursSerializer(many=True, read_only=True)

    # Filial hozir ochiq yoki yo'qligini ko'rsatuvchi maydon
    # Modelda yaratilgan 'is_open_now' metodidan qiymat oladi
    is_open = serializers.BooleanField(source='is_open_now', read_only=True)

    class Meta:
        model = Branch
        fields = [
            'id',
            'name',
            'address',
            'latitude',
            'longitude',
            'phone_number',
            'avg_preparation_minutes',  # Taxminiy vaqt uchun
            'avg_delivery_extra_minutes',  # Taxminiy vaqt uchun
            'is_active',  # Bu maydonni qoldiramiz, lekin view faqat aktivlarni oladi
            'is_open',  # Hozir ochiq yoki yo'qligi
            'working_hours'  # Ish vaqtlari ro'yxati
        ]


class OrderSerializer(serializers.ModelSerializer):
    """Buyurtma ma'lumotlarini (mahsulotlari bilan) serializatsiya qiladi."""
    # Buyurtma tarkibidagi mahsulotlar ro'yxati
    items = OrderItemSerializer(many=True, read_only=True)
    # Foydalanuvchi ma'lumotlari (ixtiyoriy, ID sini chiqaramiz)
    user = UserSerializer(read_only=True)  # Yoki user_id = serializers.PrimaryKeyRelatedField(read_only=True)

    # Status, delivery_type, payment_type uchun tushunarli nomlarni chiqarish (ixtiyoriy)
    # status_display = serializers.CharField(source='get_status_display', read_only=True)
    # delivery_type_display = serializers.CharField(source='get_delivery_type_display', read_only=True)
    # payment_type_display = serializers.CharField(source='get_payment_type_display', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id',
            'user',
            'status',  # Hozircha kodini chiqaramiz ('new', 'preparing', ...)
            # 'status_display', # Agar yuqoridagi kabi qo'shilsa
            'total_price',
            'delivery_type',
            # 'delivery_type_display',
            'address',
            'latitude',
            'longitude',
            'payment_type',
            # 'payment_type_display',
            'notes',
            'items',  # Buyurtma tarkibi
            'created_at',
            'updated_at',
        ]


class CheckoutSerializer(serializers.Serializer):
    """Checkout uchun kiruvchi ma'lumotlarni tekshiradi."""
    delivery_type = serializers.ChoiceField(
        choices=Order.DELIVERY_CHOICES,  # Modelldagi tanlovlardan olish
        required=True
    )
    address = serializers.CharField(required=False, allow_blank=True)
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    payment_type = serializers.ChoiceField(
        choices=Order.PAYMENT_CHOICES,
        required=True
    )
    notes = serializers.CharField(required=False, allow_blank=True,
                                  style={'base_template': 'textarea.html'})  # Katta matn maydoni (ixtiyoriy)

    def validate(self, data):
        """
        Umumiy validatsiya: Agar yetkazib berish tanlansa, manzil yoki lokatsiya bo'lishi kerak.
        """
        delivery_type = data.get('delivery_type')
        address = data.get('address')
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if delivery_type == 'delivery':
            if not address and not (latitude is not None and longitude is not None):
                raise serializers.ValidationError(
                    "Yetkazib berish uchun 'address' yoki 'latitude' va 'longitude' maydonlaridan biri to'ldirilishi shart."
                )
            # Agar lokatsiya berilsa, ikkalasi ham bo'lishi kerakligini tekshirish mumkin
            if (latitude is not None and longitude is None) or (latitude is None and longitude is not None):
                raise serializers.ValidationError("'latitude' va 'longitude' birga berilishi kerak.")

        # Boshqa validatsiyalarni shu yerga qo'shish mumkin
        return data
