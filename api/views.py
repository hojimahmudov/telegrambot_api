# api/views.py

from rest_framework import viewsets, permissions, generics
from rest_framework.response import Response
from django.db.models import Q  # Qidiruv uchun kerak bo'lishi mumkin

from .models import User, Category, Product
from .serializers import UserSerializer, CategorySerializer, ProductSerializer


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
