# api/serializers.py
import re
from importlib.resources import _

from rest_framework import serializers
from parler_rest.serializers import TranslatableModelSerializer
from parler_rest.fields import TranslatedFieldsField  # Til tablari uchun (ixtiyoriy)
from .models import (
    User, Category, Product, Cart, CartItem, Order, OrderItem,
    Branch, WorkingHours, UserAddress, Promotion
)


# --- User Serializer ---
class UserSerializer(serializers.ModelSerializer):
    """Foydalanuvchi ma'lumotlarini API uchun tayyorlaydi."""

    class Meta:
        model = User
        # API'da ko'rinadigan maydonlar
        fields = ['id', 'telegram_id', 'phone_number', 'username', 'first_name', 'last_name', 'language_code']
        # Ba'zi maydonlarni faqat o'qish uchun qilish mumkin (masalan, API orqali telegram_id'ni o'zgartirib bo'lmaydi)
        read_only_fields = ['telegram_id']


# --- Category Serializer ---
class CategorySerializer(TranslatableModelSerializer):
    """Kategoriya ma'lumotlarini (tarjimalari va Google Drive'dagi rasm URLi bilan) API uchun tayyorlaydi."""

    # 'image_url' maydoni endi modeldagi 'image_gdrive_url' atributidan olinadi.
    # Bu maydon faqat o'qish uchun (read_only=True), chunki u signallar orqali avtomatik to'ldiriladi.
    # Agar rasm bo'lmasa, null bo'lishi mumkin (allow_null=True).
    image_url = serializers.URLField(source='image_gdrive_url', read_only=True, allow_null=True)

    # Agar barcha tarjimalarni 'translations' kaliti ostida guruhlab chiqarmoqchi bo'lsangiz:
    # translations = TranslatedFieldsField(shared_model=Category)
    # Va 'fields' ro'yxatidan 'name' va 'slug' ni olib tashlab, 'translations' ni qo'shasiz.
    # Hozircha 'name' va 'slug' ni alohida qoldiramiz, TranslatableModelSerializer ularni
    # so'rovdagi Accept-Language sarlavhasiga qarab avtomatik tarjima qilib beradi.

    class Meta:
        model = Category
        # API'da ko'rinadigan maydonlar ro'yxati:
        fields = [
            'id',
            'name',  # Parler avtomatik joriy tildagi tarjimani oladi
            'slug',  # Parler avtomatik joriy tildagi tarjimani oladi
            'image_url',  # Endi Google Drive'dan keladigan URL
            'parent',  # Asosiy kategoriyaning ID sini ko'rsatadi.
            # Agar to'liq ma'lumotini chiqarmoqchi bo'lsak, ichki CategorySerializer ishlatish kerak bo'ladi.
            'is_active',
            'order'
        ]
        # 'name' va 'slug' maydonlari modelda translations ichida bo'lgani uchun,
        # TranslatableModelSerializer ularni to'g'ri tarjima qilib beradi.


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
    image_url = serializers.SerializerMethodField()

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

    def get_image_url(self, obj):
        request = self.context.get('request')

        # 1️⃣ Avval Google Drive URL bo‘lsa
        if obj.image_gdrive_url:
            return obj.image_gdrive_url

        # 2️⃣ Aks holda lokal rasm
        if obj.image and hasattr(obj.image, 'url'):
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url

        return None


# --- Ro'yxatdan o'tish uchun Serializer ---
class RegistrationSerializer(serializers.Serializer):
    """Ro'yxatdan o'tish uchun kiruvchi ma'lumotlarni tekshiradi."""
    telegram_id = serializers.IntegerField(required=True)
    phone_number = serializers.CharField(required=True, max_length=20)
    first_name = serializers.CharField(required=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    username = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=150)

    def validate_phone_number(self, value):
        """Telefon raqami formatini tekshirish (soddalashtirilgan misol)."""
        # Masalan, +998 bilan boshlanib, jami 13 ta raqamdan iborat bo'lsin
        if not re.match(r'^\+998\d{9}$', value):
            raise serializers.ValidationError("Telefon raqami +998XXXXXXXXX formatida bo'lishi kerak.")
        return value

    # Agar username ham unique bo'lishi kerak bo'lsa, validate qo'shish mumkin
    def validate_username(self, value):
        telegram_id = self.initial_data.get("telegram_id")

        if not value:
            return value

        qs = User.objects.filter(username=value)

        # Agar shu telegram_id bilan o‘sha user bo‘lsa — OK
        if telegram_id:
            qs = qs.exclude(telegram_id=telegram_id)

        if qs.exists():
            raise serializers.ValidationError("Bu username allaqachon boshqa foydalanuvchiga tegishli.")

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
    pickup_branch = BranchSerializer(read_only=True)

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
            'address',
            'latitude',
            'longitude',
            'payment_type',
            'notes',
            'pickup_branch',
            'estimated_ready_at',
            'estimated_delivery_at',
            'items',
            'created_at',
            'updated_at',
        ]


class CheckoutSerializer(serializers.Serializer):
    """Checkout uchun kiruvchi ma'lumotlarni tekshiradi."""
    delivery_type = serializers.ChoiceField(
        choices=Order.DELIVERY_CHOICES,
        required=True
    )
    pickup_branch_id = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.filter(is_active=True),
        source='pickup_branch',
        required=False,
        allow_null=True,
        write_only=True,
        label=_("Olib ketish filiali IDsi")
    )
    # Manzil endi majburiy emas, ixtiyoriy axborot sifatida qoladi
    address = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    # Latitude va Longitude 'delivery' uchun majburiy bo'ladi
    latitude = serializers.FloatField(required=False, allow_null=True)
    longitude = serializers.FloatField(required=False, allow_null=True)
    payment_type = serializers.ChoiceField(
        choices=Order.PAYMENT_CHOICES,
        required=True
    )
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True,
                                  style={'base_template': 'textarea.html'})

    def validate(self, data):
        """
        Umumiy validatsiya: Yetkazib berish turi, lokatsiya va filial holatini tekshiradi.
        """
        delivery_type = data.get('delivery_type')
        pickup_branch = data.get('pickup_branch')
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if delivery_type == 'delivery':
            # --- YETKAZIB BERISH UCHUN YANGI TEKSHIRUV ---
            if latitude is None or longitude is None:
                # Agar lat yoki lon kelmasa, xatolik beramiz
                raise serializers.ValidationError({
                    "latitude": [_("Yetkazib berish uchun majburiy maydon.")],
                    "longitude": [_("Yetkazib berish uchun majburiy maydon.")]
                })
            # --------------------------------------------
            if pickup_branch:
                raise serializers.ValidationError(
                    {"pickup_branch_id": _("Yetkazib berish tanlanganda filial ko'rsatilmasligi kerak.")}
                )

        elif delivery_type == 'pickup':
            if not pickup_branch:
                raise serializers.ValidationError(
                    {"pickup_branch_id": _("Olib ketish uchun filial tanlanishi shart.")}
                )
            # Pickup uchun lokatsiya kiritilmasligini tekshirish
            if latitude is not None or longitude is not None:
                raise serializers.ValidationError({
                    "latitude": [_("Olib ketish tanlanganda lokatsiya kiritilmaydi.")],
                    "longitude": [_("Olib ketish tanlanganda lokatsiya kiritilmaydi.")]
                }
                )
            # Filial ochiqligini tekshirish
            if not pickup_branch.is_open_now():
                raise serializers.ValidationError(
                    {"pickup_branch_id": _("Tanlangan filial hozirda yopiq.")}
                )

        return data


class UserAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAddress
        fields = ['id', 'user', 'name', 'address_text', 'latitude', 'longitude', 'created_at']
        read_only_fields = ['user', 'created_at']  # User avtomatik o'rnatiladi

    def validate(self, data):
        # Foydalanuvchi o'zining manzillarini boshqarishi kerak
        # Bu tekshiruv ViewSet da permission orqali qilinadi, bu yerda shart emas
        # lekin qo'shimcha validatsiya qo'shish mumkin
        return data


class PromotionSerializer(TranslatableModelSerializer):
    is_currently_active = serializers.BooleanField(read_only=True)
    image_url = serializers.URLField(source='image_gdrive_url', read_only=True, allow_null=True)

    class Meta:
        model = Promotion
        fields = ['id', 'title', 'description',
                  'image_url',
                  'start_date', 'end_date', 'is_active', 'is_currently_active']
