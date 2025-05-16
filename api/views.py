# api/views.py

from rest_framework import viewsets, permissions, generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q
from .tasks import send_otp_telegram_task
from .utils import send_telegram_otp, logger
from django.utils import timezone
import random
from rest_framework_simplejwt.tokens import RefreshToken
from django.db import transaction  # <-- Ma'lumotlar bazasi tranzaksiyalari uchun
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal  # <-- Narxlar bilan ishlash uchun

# Modellarni import qilamiz
from .models import (
    User, Category, Product, Cart, CartItem,
    Order, OrderItem, Branch
)
# Serializer'larni import qilamiz
from .serializers import (
    UserSerializer, CategorySerializer, ProductSerializer,
    RegistrationSerializer, OTPVerificationSerializer,
    CartSerializer, CartItemSerializer,
    OrderSerializer, OrderItemSerializer, CheckoutSerializer, BranchSerializer
)


# --- Category ViewSet ---
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Barcha aktiv kategoriyalarni ko'rish uchun API endpoint.
    ReadOnlyModelViewSet faqat list() va retrieve() action'larini taqdim etadi.
    """
    queryset = Category.objects.filter(is_active=True).prefetch_related('translations')  # Aktiv kategoriyalar
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]  # Hamma ko'rishi mumkin

    # Tilni header orqali avtomatik aniqlaydi (parler-rest yordamida)


# --- Product ViewSet ---
class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Barcha mavjud mahsulotlarni ko'rish uchun API endpoint.
    Kategoriya bo'yicha filtrlash mumkin (?category_id=...).
    """
    serializer_class = ProductSerializer
    permission_classes = [permissions.AllowAny]  # Hamma ko'rishi mumkin

    def get_queryset(self):
        """
        Mavjud mahsulotlarni qaytaradi, agar 'category_id' parametri
        bo'lsa, faqat shu kategoriyadagi mahsulotlarni qaytaradi.
        """
        queryset = Product.objects.filter(is_available=True).prefetch_related('translations',
                                                                              'category__translations')  # Mavjud mahsulotlar

        category_id = self.request.query_params.get('category_id')
        if category_id is not None:
            try:
                # category_id raqam ekanligini tekshirish
                category_id = int(category_id)
                queryset = queryset.filter(category_id=category_id)
            except ValueError:
                # Agar category_id raqam bo'lmasa, e'tibor bermaymiz yoki xatolik qaytarish mumkin
                pass  # Yoki: return Product.objects.none()

        # Qidiruv (?search=...) qo'shish mumkin
        search_query = self.request.query_params.get('search')
        if search_query:
            # Nom yoki tavsifda qidirish (har ikkala tilda)
            queryset = queryset.filter(
                Q(translations__name__icontains=search_query) |
                Q(translations__description__icontains=search_query)
            ).distinct()  # distinct() dublikatlarni oldini olish uchun

        return queryset

    # Tilni header orqali avtomatik aniqlaydi (parler-rest yordamida)


# --- User Profile View ---
class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Autentifikatsiyadan o'tgan foydalanuvchining profilini olish va
    yangilash uchun API endpoint (faqat o'z profilini).
    """
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]  # Faqat login qilganlar kira oladi

    def get_object(self):
        # Har doim so'rov yuborayotgan foydalanuvchini qaytaradi
        return self.request.user

    # Yangilash (Update - PUT/PATCH) logikasi RetrieveUpdateAPIView tomonidan ta'minlanadi
    # Faqat ruxsat etilgan maydonlar (serializerda ko'rsatilgan) yangilanadi


class RegistrationView(APIView):
    """
    Yangi foydalanuvchini ro'yxatdan o'tkazish va OTP yuborish uchun endpoint.
    Foydalanuvchi aktiv bo'lmagan holatda yaratiladi yoki yangilanadi.
    """
    permission_classes = [permissions.AllowAny]  # Hamma ro'yxatdan o'tishi mumkin

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        if serializer.is_valid():
            validated_data = serializer.validated_data
            phone_number = validated_data['phone_number']
            telegram_id = validated_data['telegram_id']

            existing_user_by_tg = User.objects.filter(telegram_id=telegram_id).first()
            if existing_user_by_tg and existing_user_by_tg.phone_number != phone_number:
                return Response(
                    {"error": "Bu Telegram ID allaqachon boshqa raqam bilan ro'yxatdan o'tgan."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user_instance_was_found = False
            try:
                # Telefon raqami bo'yicha foydalanuvchini qidiramiz
                user = User.objects.get(phone_number=phone_number)
                if user.is_active:
                    # Agar foydalanuvchi aktiv bo'lsa, xatolik qaytaramiz
                    return Response(
                        {"error": "Bu telefon raqami bilan allaqachon aktiv foydalanuvchi mavjud."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                # Agar aktiv bo'lmasa (oldingi tugallanmagan ro'yxatdan o'tish),
                # ma'lumotlarini yangilab, yangi OTP yuboramiz
                user_instance_was_found = True
                user.telegram_id = telegram_id
                user.first_name = validated_data.get('first_name', user.first_name)
                user.last_name = validated_data.get('last_name', user.last_name)
                # Username'ni yangilash yoki generatsiya qilish
                username = validated_data.get('username') or f"user_{telegram_id}"
                if User.objects.filter(username=username).exclude(pk=user.pk).exists():
                    username = f"{username}_{random.randint(100, 999)}"  # Agar band bo'lsa
                user.username = username
                user.set_unusable_password()  # Parolni o'rnatmaymiz, chunki OTP ishlatiladi
                # user.save() # OTP o'rnatilgandan keyin saqlaymiz

            except User.DoesNotExist:
                # Agar foydalanuvchi mavjud bo'lmasa, yangisini yaratamiz
                username = validated_data.get('username') or f"user_{telegram_id}"
                if User.objects.filter(username=username).exists():
                    username = f"{username}_{random.randint(100, 999)}"

                user = User(
                    telegram_id=telegram_id,
                    phone_number=phone_number,
                    first_name=validated_data.get('first_name'),
                    last_name=validated_data.get('last_name'),
                    username=username,
                    is_active=False  # Muhim: Aktiv emas!
                )
                user.set_unusable_password()  # Parol o'rnatilmaydi

            # --- OTP Generatsiya va Saqlash ---
            otp = random.randint(100000, 999999)  # 6 xonali OTP
            user.otp_code = str(otp)
            user.otp_created_at = timezone.now()

            if user_instance_was_found:  # Yoki user.pk is not None deb tekshirish mumkin
                # Agar foydalanuvchi avvaldan mavjud bo'lsa (aktiv emas),
                # kerakli maydonlarni yangilaymiz
                fields_to_update = [
                    'otp_code', 'otp_created_at', 'first_name', 'last_name',
                    'username', 'telegram_id'
                    # 'is_active' ni bu yerda o'zgartirmaymiz, u False bo'lib turishi kerak
                ]
                user.save(update_fields=fields_to_update)
            else:
                # Agar yangi foydalanuvchi bo'lsa, hamma maydonlarni saqlaymiz (INSERT)
                user.save()

            # Yangi chaqiruv (asinxron)
            send_otp_telegram_task.delay(user.telegram_id, otp)
            logger.info(f"Celery task to send OTP to {user.telegram_id} has been dispatched.")
            # ----------------------------------------

            return Response(
                {"message": f"Tasdiqlash kodi {phone_number} raqamiga Telegram orqali yuborildi."},
                status=status.HTTP_200_OK
            )
        # Agar serializer validatsiyadan o'tmasa
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OTPVerificationView(APIView):
    """
    Telefon raqami va OTP kod yordamida foydalanuvchini tasdiqlash
    va JWT tokenlarini qaytarish uchun endpoint.
    """
    permission_classes = [permissions.AllowAny]  # Hamma OTP ni tasdiqlashi mumkin

    def post(self, request):
        serializer = OTPVerificationSerializer(data=request.data)
        if serializer.is_valid():
            phone_number = serializer.validated_data['phone_number']
            otp_code = serializer.validated_data['otp_code']

            try:
                # Aktiv bo'lmagan foydalanuvchini telefon raqami bo'yicha topamiz
                user = User.objects.get(phone_number=phone_number, is_active=False)
            except User.DoesNotExist:
                return Response(
                    {"error": "Bunday raqamli aktiv bo'lmagan foydalanuvchi topilmadi."},
                    status=status.HTTP_404_NOT_FOUND  # 404 Not Found ishlatgan ma'qulroq
                )

            # Model ichidagi metod orqali OTP ni tekshiramiz (muddati ham tekshiriladi)
            if user.is_otp_valid(otp_code):
                # Foydalanuvchini aktiv qilamiz
                user.is_active = True
                user.save(update_fields=['is_active'])
                # OTP kodni tozalaymiz
                user.clear_otp()

                # --- JWT Tokenlarini Generatsiya Qilish ---
                refresh = RefreshToken.for_user(user)
                access_token = str(refresh.access_token)
                # --------------------------------------

                # Foydalanuvchi ma'lumotlarini javob uchun tayyorlaymiz
                user_serializer = UserSerializer(user)

                return Response({
                    'message': "Foydalanuvchi muvaffaqiyatli tasdiqlandi!",
                    'access_token': access_token,
                    'refresh_token': str(refresh),
                    'user': user_serializer.data
                }, status=status.HTTP_200_OK)
            else:
                # Agar OTP noto'g'ri yoki muddati o'tgan bo'lsa
                return Response(
                    {"error": "Noto'g'ri yoki muddati o'tgan OTP kod."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        # Agar serializer validatsiyadan o'tmasa
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CartView(APIView):
    """
    Foydalanuvchining savatchasi bilan ishlash uchun View.
    GET: Savatni ko'rish.
    POST: Savatga mahsulot qo'shish (yoki sonini oshirish).
    PATCH: Savatdagi mahsulot sonini o'zgartirish.
    DELETE: Savatdagi mahsulotni o'chirish.
    """
    permission_classes = [permissions.IsAuthenticated]  # Faqat login qilgan foydalanuvchilar

    def get_or_create_cart(self, user):
        """Berilgan foydalanuvchi uchun savatni oladi yoki yaratadi."""
        cart, created = Cart.objects.get_or_create(user=user)
        return cart

    # --- GET Method: Savatni ko'rish ---
    def get(self, request):
        user = request.user
        # --- Savatni olamiz (yoki yaratamiz) VA OPTIMALLASHTIRAMIZ ---
        try:
            # Avval get_or_create bilan savatni olamiz yoki yaratamiz
            cart, created = Cart.objects.get_or_create(user=user)
            if created:
                # Agar yangi yaratilgan bo'lsa, logga yozamiz
                logger.info(f"Created new cart (ID: {cart.pk}) for user {user.pk}")

            # Endi shu savatni (yoki topilganini) optimallashtirilgan holda qayta olamiz
            # Bu serializer ishlashi uchun kerakli barcha ma'lumotlarni oldindan yuklaydi
            cart_to_serialize = Cart.objects.select_related(
                'user'  # Foydalanuvchi ma'lumotini ham birga olish uchun
            ).prefetch_related(
                'items',  # Barcha CartItem'lar
                'items__product',  # Ularning Product'lari
                'items__product__translations',  # Product tarjimalari
                'items__product__category',  # Product kategoriyalari
                'items__product__category__translations'  # Kategoriya tarjimalari
            ).get(pk=cart.pk)  # pk orqali aynan shu savatni olamiz

        except Cart.DoesNotExist:  # get_or_create dan keyin bu bo'lmasligi kerak, lekin ehtiyot shart
            logger.error(f"Cart somehow not found or created for user {user.pk}")
            return Response({"error": "Savat topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # Boshqa kutilmagan xatoliklar
            logger.error(f"Error getting/creating/prefetching cart for user {user.pk}: {e}", exc_info=True)
            return Response({"error": "Savatni olishda xatolik."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Optimallashtirilgan savatni serializerga beramiz
        serializer = CartSerializer(cart_to_serialize, context={'request': request})
        return Response(serializer.data)

    # --- POST Method: Savatga mahsulot qo'shish ---
    def post(self, request):
        cart = self.get_or_create_cart(request.user)
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)  # Agar quantity kelmasa, 1 deb olamiz

        if not product_id:
            return Response({"error": "product_id maydoni majburiy."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            quantity = int(quantity)
            if quantity <= 0:
                raise ValueError("Miqdor musbat bo'lishi kerak")
        except (TypeError, ValueError):
            return Response({"error": "quantity musbat butun son bo'lishi kerak."}, status=status.HTTP_400_BAD_REQUEST)

        product = get_object_or_404(Product, pk=product_id,
                                    is_available=True)  # Mahsulotni topamiz (mavjud bo'lishi kerak)

        # Savatda bu mahsulot bor yoki yo'qligini tekshiramiz
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity}  # Agar yo'q bo'lsa, shu quantity bilan yaratiladi
        )

        if not created:
            # Agar mahsulot savatda mavjud bo'lsa, sonini oshiramiz
            cart_item.quantity += quantity
            cart_item.save()

        serializer = CartSerializer(cart, context={'request': request})
        # Yaratilgan bo'lsa 201, yangilangan bo'lsa 200 qaytarish mumkin, lekin 200 ham OK
        return Response(serializer.data, status=status.HTTP_200_OK)

    # --- PATCH Method: Savatdagi mahsulot sonini o'zgartirish ---
    @transaction.atomic
    def patch(self, request):
        item_id = request.data.get('item_id')
        change = request.data.get('change')  # Yangi miqdor o'rniga o'zgarish (+1 yoki -1)

        if not item_id or change is None:
            return Response({"error": "item_id va change maydonlari majburiy."}, status=status.HTTP_400_BAD_REQUEST)

        cart = self.get_or_create_cart(request.user)
        cart_item = get_object_or_404(CartItem, pk=item_id, cart=cart)
        new_quantity = cart_item.quantity + change

        if new_quantity < 1:
            cart_item.delete()
            logger.info(f"CartItem {item_id} deleted via PATCH.")
        else:
            cart_item.quantity = new_quantity
            cart_item.save(update_fields=['quantity'])
            logger.info(f"CartItem {item_id} quantity updated to {new_quantity}.")

        # --- JAVOB QAYTARISHDAN OLDIN OPTIMALLASHTIRISH ---
        # Savatning yangilangan holatini optimallashtirilgan so'rov bilan olamiz
        try:
            cart_to_serialize = Cart.objects.select_related(  # ForeignKey uchun
                'user'
            ).prefetch_related(  # ManyToMany yoki teskari ForeignKey uchun
                'items',  # Savatdagi itemlar
                'items__product',  # Har bir item uchun mahsulot
                'items__product__translations',  # Mahsulot tarjimalari
                'items__product__category',  # Mahsulot kategoriyasi
                'items__product__category__translations'  # Kategoriya tarjimalari
            ).get(pk=cart.pk)  # Aynan shu savatni olamiz
        except Cart.DoesNotExist:  # Agar savat qandaydir tarzda o'chib ketgan bo'lsa
            return Response({"error": "Savat topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CartSerializer(cart_to_serialize, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    # --- DELETE Method: Savatdagi mahsulotni o'chirish ---
    @transaction.atomic
    def delete(self, request):
        item_id = request.data.get('item_id')

        if not item_id:
            return Response({"error": "item_id maydoni majburiy."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        cart = self.get_or_create_cart(user)
        cart_item = get_object_or_404(CartItem, pk=item_id, cart=cart)
        item_pk_for_log = cart_item.pk
        cart_item.delete()
        logger.info(f"CartItem {item_pk_for_log} deleted by user {user.id}.")

        # --- JAVOB QAYTARISHDAN OLDIN OPTIMALLASHTIRISH ---
        try:
            cart_to_serialize = Cart.objects.select_related(
                'user'
            ).prefetch_related(
                'items',
                'items__product__translations',
                'items__product__category__translations'
            ).get(pk=cart.pk)
        except Cart.DoesNotExist:
            return Response({"error": "Savat topilmadi (o'chirishdan keyin)."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CartSerializer(cart_to_serialize, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        user = request.user
        try:
            cart = user.cart
            cart_items = cart.items.all()
            if not cart_items.exists():
                return Response({"error": "Buyurtma berish uchun savat bo'sh."}, status=status.HTTP_400_BAD_REQUEST)
        except Cart.DoesNotExist:
            return Response({"error": "Savat topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        # --- Kiruvchi ma'lumotlarni validatsiya qilamiz (pickup_branch ham tekshiriladi) ---
        checkout_serializer = CheckoutSerializer(data=request.data,
                                                 context={'request': request})  # Context qo'shish mumkin
        if not checkout_serializer.is_valid():
            return Response(checkout_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = checkout_serializer.validated_data
        delivery_type = validated_data.get('delivery_type')
        pickup_branch = validated_data.get('pickup_branch')  # Bu yerda Branch obyekti keladi

        # --- Order uchun ma'lumotlarni tayyorlaymiz ---
        order_data = {
            'user': user,
            'status': 'new',
            'total_price': cart.total_price,
            'delivery_type': delivery_type,
            'address': validated_data.get('address'),
            'latitude': validated_data.get('latitude'),
            'longitude': validated_data.get('longitude'),
            'payment_type': validated_data.get('payment_type'),
            'notes': validated_data.get('notes')
        }
        # Agar pickup bo'lsa, filialni qo'shamiz
        if delivery_type == 'pickup' and pickup_branch:
            order_data['pickup_branch'] = pickup_branch

        # --- Order yaratamiz ---
        try:
            order = Order.objects.create(**order_data)
        except Exception as e:
            return Response({"error": f"Buyurtma yaratishda xatolik: {e}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # --- OrderItem'larni yaratamiz ---
        order_items_to_create = []
        for cart_item in cart_items:
            if not cart_item.product or not cart_item.product.is_available:
                return Response(
                    {
                        "error": f"Mahsulot '{cart_item.product.name if cart_item.product else 'Nomalum'}' buyurtma paytida mavjud emas."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            item_total_price = cart_item.product.price * cart_item.quantity
            order_items_to_create.append(
                OrderItem(
                    order=order,
                    product=cart_item.product,
                    quantity=cart_item.quantity,
                    price_per_unit=cart_item.product.price,
                    total_price=item_total_price
                )
            )
        try:
            OrderItem.objects.bulk_create(order_items_to_create)
        except Exception as e:
            return Response({"error": f"Buyurtma mahsulotlarini yaratishda xatolik: {e}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # --- Taxminiy vaqtni hisoblaymiz va saqlaymiz ---
        relevant_branch = None
        if delivery_type == 'pickup':
            relevant_branch = pickup_branch
        # TODO: Agar delivery bo'lsa, qaysi filialdan yetkazilishini aniqlash logikasi kerak
        # Hozircha faqat pickup uchun hisoblaymiz yoki standart filial belgilash mumkin
        # Masalan, ID si 1 bo'lgan filialni standart deb olaylik (agar pickup_branch bo'lmasa)
        # elif Branch.objects.filter(is_active=True).exists():
        #      relevant_branch = Branch.objects.filter(is_active=True).first()

        if relevant_branch:
            try:
                now = timezone.now()
                prep_time = timedelta(minutes=relevant_branch.avg_preparation_minutes)
                order.estimated_ready_at = now + prep_time

                if delivery_type == 'delivery':
                    delivery_time = timedelta(minutes=relevant_branch.avg_delivery_extra_minutes)
                    order.estimated_delivery_at = order.estimated_ready_at + delivery_time

                order.save(update_fields=['estimated_ready_at', 'estimated_delivery_at'])
            except Exception as e:
                # Taxminiy vaqtni hisoblashda xato bo'lsa ham, buyurtma yaratildi deb hisoblaymiz
                # Lekin logga yozib qo'yish kerak
                print(f"Error calculating estimated time for order {order.id}: {e}")

        # --- Savatni tozalaymiz ---
        cart_items.delete()

        # --- Yaratilgan buyurtmani qaytaramiz ---
        order_serializer = OrderSerializer(order, context={'request': request})
        return Response(order_serializer.data, status=status.HTTP_201_CREATED)


class OrderHistoryView(generics.ListAPIView):
    """
    Autentifikatsiyadan o'tgan foydalanuvchining buyurtmalar tarixini
    ro'yxat ko'rinishida qaytaradi (paginatsiya bilan).
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]  # Faqat login qilganlar ko'ra oladi
    # Paginatsiyani sozlash mumkin (agar settings.py da global belgilanmagan bo'lsa)
    pagination_class = PageNumberPagination  # yoki boshqa turdagi pagination

    def get_queryset(self):
        """
        Faqat joriy foydalanuvchiga tegishli buyurtmalarni,
        yangi yaratilganlari birinchi bo'lib qaytaradi.
        Optimalizatsiya uchun bog'liq ma'lumotlarni oldindan oladi.
        """
        user = self.request.user
        return Order.objects.filter(user=user).order_by('-created_at').prefetch_related(
            'items',  # OrderItem'larni olish uchun
            'items__product__translations',  # Mahsulot tarjimalarini olish uchun
            'items__product__category__translations',  # Kategoriya tarjimalarini olish uchun
            'pickup_branch__working_hours'  # Filial ish vaqtlarini olish uchun (agar kerak bo'lsa)
        )


class OrderDetailView(generics.RetrieveAPIView):
    """
    Autentifikatsiyadan o'tgan foydalanuvchiga tegishli bo'lgan yagona
    buyurtmaning batafsil ma'lumotlarini qaytaradi.
    """
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]  # Faqat buyurtma egasi ko'ra oladi
    lookup_field = 'pk'  # URL'dan qaysi maydon orqali qidirish (standart 'pk', ya'ni ID)

    def get_queryset(self):
        """
        Faqat joriy foydalanuvchiga tegishli buyurtmalarni qidirish uchun
        queryset'ni filterlaydi. Bu boshqa birovning buyurtmasini
        ID sini topib ko'rishning oldini oladi.
        """
        user = self.request.user
        # History'dagiga o'xshash prefetch qo'shamiz
        return Order.objects.filter(user=user).prefetch_related(
            'items',
            'items__product__translations',
            'items__product__category__translations',
            'pickup_branch__working_hours'
        )


class OrderCancelView(APIView):
    """
    Foydalanuvchiga o'ziga tegishli buyurtmani bekor qilish (cancel)
    uchun endpoint (faqat 'new' statusida bo'lsa).
    """
    permission_classes = [permissions.IsAuthenticated]  # Faqat login qilganlar

    def post(self, request, pk=None):
        """
        POST so'rovi kelganda buyurtmani bekor qilishga harakat qiladi.
        'pk' URL'dan olinadi (buyurtma IDsi).
        """
        user = request.user
        # Buyurtmani topamiz va u shu foydalanuvchiga tegishli ekanligini tekshiramiz
        order = get_object_or_404(Order, pk=pk, user=user)

        # Buyurtma statusini tekshiramiz
        if order.status == 'new':
            # Agar status 'new' bo'lsa, bekor qilamiz
            order.status = 'cancelled'
            order.save(update_fields=['status'])  # Faqat status maydonini yangilaymiz
            # Muvaffaqiyatli javob qaytaramiz
            return Response(
                {"message": "Buyurtma muvaffaqiyatli bekor qilindi.", "status": order.status},
                status=status.HTTP_200_OK
            )
        else:
            # Agar status 'new' bo'lmasa, xatolik qaytaramiz
            return Response(
                {"error": f"'{order.get_status_display()}' holatidagi buyurtmani bekor qilib bo'lmaydi."},
                status=status.HTTP_400_BAD_REQUEST
            )


class BranchViewSet(viewsets.ReadOnlyModelViewSet):  # <-- ListAPIView o'rniga
    """
    Barcha aktiv filiallar ro'yxatini va bitta filialni ID bo'yicha olish uchun.
    """
    queryset = Branch.objects.filter(is_active=True).prefetch_related('working_hours')
    serializer_class = BranchSerializer
    permission_classes = [permissions.AllowAny]
    # lookup_field = 'pk' # Bu standart, shart emas
