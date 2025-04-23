# api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
# View'larni import qilamiz
from .views import (
    CategoryViewSet, ProductViewSet, UserProfileView,
    RegistrationView, OTPVerificationView, CartView, CheckoutView  # <-- Yangi View'lar
)
# simplejwt view'larini import qilamiz (token refresh uchun)
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

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

    # --- Autentifikatsiya Endpoint'lari ---
    path('auth/register/', RegistrationView.as_view(), name='auth-register'),
    path('auth/verify/', OTPVerificationView.as_view(), name='auth-verify'),

    # --- JWT Token Endpoint'lari ---
    # Agar username/password login kerak bo'lsa (hozir bizda OTP orqali)
    # path('auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),  # Access tokenni yangilash uchun

    # --- Savat Endpoint'i ---
    path('cart/', CartView.as_view(), name='user-cart'),
    # --- Yangi Checkout Endpoint'i ---
    path('orders/checkout/', CheckoutView.as_view(), name='order-checkout'),
]
