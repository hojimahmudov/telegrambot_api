# api/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from parler.admin import TranslatableAdmin  # <-- Importni qaytaramiz
from .models import User, Category, Product


# UserAdmin o'zgarishsiz qoladi
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'telegram_id', 'phone_number', 'first_name', 'last_name', 'is_staff', 'is_active')
    search_fields = ('username', 'telegram_id', 'phone_number', 'first_name', 'last_name')
    list_filter = ('is_staff', 'is_active', 'groups')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Qo\'shimcha ma\'lumotlar', {'fields': ('telegram_id', 'phone_number')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Majburiy ma\'lumotlar', {'fields': ('telegram_id', 'phone_number', 'first_name')}),
    )


# CategoryAdmin o'zgarishsiz qoladi
@admin.register(Category)
class CategoryAdmin(TranslatableAdmin):
    list_display = ('name', 'is_active', 'order')
    list_filter = ('is_active',)
    search_fields = ('translations__name',)
    list_editable = ('is_active', 'order')


# ProductAdmin'ni TranslatableAdmin'ga qaytaramiz va sozlamalarni tiklaymiz
@admin.register(Product)
class ProductAdmin(TranslatableAdmin):  # <-- TranslatableAdmin'dan meros olamiz
    list_display = ('name', 'category', 'price', 'is_available')  # <-- 'name'ni qaytaramiz
    list_filter = ('category', 'is_available')
    search_fields = ('translations__name', 'translations__description', 'category__translations__name')
    list_editable = ('price', 'is_available')
