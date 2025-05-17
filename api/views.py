# api/views.py

from rest_framework import viewsets, permissions, generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.db import IntegrityError
from .utils import logger
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
    Order, OrderItem, Branch, UserAddress
)
# Serializer'larni import qilamiz
from .serializers import (
    UserSerializer, CategorySerializer, ProductSerializer,
    RegistrationSerializer, OTPVerificationSerializer,
    CartSerializer, CartItemSerializer,
    OrderSerializer, OrderItemSerializer, CheckoutSerializer, BranchSerializer, UserAddressSerializer
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


class PhoneLoginOrRegisterView(APIView):  # Eski RegistrationView o'rniga
    permission_classes = [AllowAny]

    def _generate_unique_username(self, base_username: str, current_user_pk: int | None = None) -> str:
        # Bu funksiya avvalgidek qoladi
        username_to_try = base_username
        counter = 1
        while True:
            qs = User.objects.filter(username=username_to_try)
            if current_user_pk:
                qs = qs.exclude(pk=current_user_pk)
            if not qs.exists():
                return username_to_try
            username_to_try = f"{base_username}_{counter}"
            counter += 1

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        phone_number = validated_data['phone_number']
        telegram_id = validated_data['telegram_id']
        first_name = validated_data.get('first_name')
        last_name = validated_data.get('last_name')
        username_from_bot = validated_data.get('username')

        # Telegram ID unikalligini tekshirish (avvalgidek)
        conflicting_user_by_tg_id = User.objects.filter(telegram_id=telegram_id).exclude(
            phone_number=phone_number).first()
        if conflicting_user_by_tg_id:
            return Response(
                {"error": "Bu Telegram ID allaqachon boshqa telefon raqamiga bog'langan."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = None
        created = False
        try:
            user = User.objects.get(phone_number=phone_number)
            # Foydalanuvchi mavjud. Ma'lumotlarini yangilaymiz (agar kerak bo'lsa).
            user.telegram_id = telegram_id  # Agar o'zgargan bo'lsa
            user.first_name = first_name if first_name else user.first_name
            user.last_name = last_name if last_name is not None else user.last_name

            base_username_for_update = username_from_bot if username_from_bot else user.username
            if not base_username_for_update:
                base_username_for_update = f"user_{telegram_id}"
            user.username = self._generate_unique_username(base_username_for_update, user.pk)
            user.is_active = True  # DARHOL AKTIV QILAMIZ

        except User.DoesNotExist:
            # Yangi foydalanuvchi
            base_username_for_new = username_from_bot if username_from_bot else f"user_{telegram_id}"
            final_username = self._generate_unique_username(base_username_for_new)

            user = User(
                telegram_id=telegram_id,
                phone_number=phone_number,
                first_name=first_name,
                last_name=last_name,
                username=final_username,
                is_active=True  # DARHOL AKTIV QILAMIZ
            )
            user.set_unusable_password()
            created = True

        try:
            user.save()  # To'liq saqlaymiz
        except IntegrityError as e:
            logger.error(f"IntegrityError on saving user {getattr(user, 'username', 'N/A')}: {e}", exc_info=True)
            # ... (avvalgi IntegrityError ni qayta ishlash logikasi) ...
            return Response({"error": "Foydalanuvchini saqlashda DB xatoligi."}, status=status.HTTP_400_BAD_REQUEST)

        logger.info(
            f"User {user.username} (TGID: {user.telegram_id}) {'created and' if created else 'found and'} activated.")

        # --- ENDI TOKENLARNI GENERATSIYA QILIB QAYTARAMIZ ---
        refresh = RefreshToken.for_user(user)
        user_serializer = UserSerializer(user)  # Foydalanuvchi ma'lumotlari uchun

        return Response({
            'message': "Muvaffaqiyatli tizimga kirdingiz!" if not created else "Muvaffaqiyatli ro'yxatdan o'tdingiz!",
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user': user_serializer.data
        }, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)


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
        if delivery_type == 'pickup' and pickup_branch:  # pickup_branch bu Branch obyekt
            relevant_branch = pickup_branch
        elif delivery_type == 'delivery':
            logger.info(f"Delivery order {order.id}. Finding a relevant branch for time estimation.")
            # Avval aktiv filiallarni olamiz. Ish vaqtlarini ham oldindan olamiz, chunki is_open_now() ularni ishlatadi.
            active_branches = Branch.objects.filter(is_active=True).prefetch_related('working_hours')

            # --- OCHIQ FILIALNI TOPISH LOGIKASI ---
            found_open_branch = False
            for branch_candidate in active_branches:
                if branch_candidate.is_open_now():  # Model metodini chaqiramiz
                    relevant_branch = branch_candidate
                    logger.info(
                        f"Delivery order {order.id} assigned to OPEN branch {relevant_branch.name} (ID: {relevant_branch.id}) for time estimation.")
                    found_open_branch = True
                    break  # Ochiq filial topildi, qidirishni to'xtatamiz

            if not found_open_branch and active_branches.exists():
                # Agar ochiq filial topilmasa, lekin aktiv filiallar bo'lsa, birinchisini olamiz
                relevant_branch = active_branches.first()
                logger.warning(
                    f"No OPEN branches found for delivery order {order.id}. "
                    f"Using first ACTIVE branch {relevant_branch.name} (ID: {relevant_branch.id}) for estimation (this branch might be closed)."
                )
            elif not active_branches.exists():  # Agar umuman aktiv filial bo'lmasa
                logger.warning(
                    f"No active branches available AT ALL to handle delivery order {order.id} for time estimation.")
            # -----------------------------------------

        # Buyurtma obyektida bu maydonlar borligiga ishonch hosil qilamiz (null=True bo'lsa ham)
        order.estimated_ready_at = None
        order.estimated_delivery_at = None
        fields_to_update_for_estimates = []

        if relevant_branch:
            # ... (taxminiy vaqtlarni hisoblash va saqlash logikasi #237-javobdagidek qoladi) ...
            # Bu qism o'zgarishsiz:
            try:
                now = timezone.now()
                prep_minutes = relevant_branch.avg_preparation_minutes
                if prep_minutes is None: prep_minutes = 30
                prep_time = timedelta(minutes=prep_minutes)
                order.estimated_ready_at = now + prep_time
                fields_to_update_for_estimates.append('estimated_ready_at')

                if delivery_type == 'delivery':
                    delivery_extra_minutes = relevant_branch.avg_delivery_extra_minutes
                    if delivery_extra_minutes is None: delivery_extra_minutes = 20
                    delivery_time = timedelta(minutes=delivery_extra_minutes)
                    order.estimated_delivery_at = order.estimated_ready_at + delivery_time
                    fields_to_update_for_estimates.append('estimated_delivery_at')

                if fields_to_update_for_estimates:
                    order.save(update_fields=fields_to_update_for_estimates)
                    logger.info(
                        f"Estimated times saved for order {order.id}: Ready at {order.estimated_ready_at}, Delivery at {order.estimated_delivery_at}")
            except Exception as e:
                logger.error(f"Error calculating or saving estimated time for order {order.id}: {e}", exc_info=True)
        else:
            logger.warning(f"No relevant branch determined for order {order.id}, cannot calculate estimated times.")

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


class UserAddressViewSet(viewsets.ModelViewSet):
    """
    Foydalanuvchining saqlangan manzillarini boshqarish uchun endpoint.
    Foydalanuvchi faqat o'zining manzillarini ko'ra oladi va boshqara oladi.
    """
    serializer_class = UserAddressSerializer
    permission_classes = [permissions.IsAuthenticated]  # Faqat login qilganlar uchun

    def get_queryset(self):
        """Faqat joriy foydalanuvchiga tegishli manzillarni qaytaradi."""
        return UserAddress.objects.filter(user=self.request.user).order_by('-created_at')

    def perform_create(self, serializer):
        """Manzil yaratilayotganda uni joriy foydalanuvchiga bog'laydi."""
        serializer.save(user=self.request.user)
