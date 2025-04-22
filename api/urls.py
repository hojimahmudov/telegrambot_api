# api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ProductViewSet, UserProfileView

# Router obyektini yaratamiz
router = DefaultRouter()

# ViewSet'larni router'ga ro'yxatdan o'tkazamiz
# router.register(prefix, viewset, basename)
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'products', ProductViewSet, basename='product')

# URL pattern'lari ro'yxati
urlpatterns = [
    # Router tomonidan generatsiya qilingan URL'larni qo'shamiz
    # Bu /api/v1/categories/ va /api/v1/products/ kabi manzillarni yaratadi
    path('', include(router.urls)),

    # Alohida View uchun URL manzil
    path('users/profile/', UserProfileView.as_view(), name='user-profile'),

    # Kelajakda boshqa URL'lar shu yerga qo'shiladi (masalan, buyurtmalar uchun)
]
