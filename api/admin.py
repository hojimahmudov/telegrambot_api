# api/admin.py
from django import forms
from django.contrib import admin
from django.forms.models import BaseInlineFormSet  # <-- BaseInlineFormSet'ni import qilamiz
from django.core.exceptions import ValidationError  # <-- ValidationError'ni import qilamiz
from django.utils.translation import gettext_lazy as _
import datetime  # <-- datetime'ni import qilamiz
from datetime import time, timedelta  # <-- time va timedelta'ni ham import qilamiz

# Modellar importi
from .models import (
    User, Category, Product, Branch, WorkingHours, Order, OrderItem
)

# Parler Admin importlari (agar kerak bo'lsa)
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from parler.admin import TranslatableAdmin


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


# WorkingHours modelini Branch adminida inline ko'rsatish uchun
def time_choices(interval_minutes=30):
    """Belgilangan interval bilan vaqt tanlovlarini generatsiya qiladi."""
    choices = []
    # datetime.time obyektlari bilan ishlash aniqroq
    current_time = time(0, 0)
    end_time = time(23, 30)
    interval = timedelta(minutes=interval_minutes)

    while current_time <= end_time:
        time_str = current_time.strftime("%H:%M")
        choices.append((current_time, time_str))  # Qiymat sifatida time obyektini saqlaymiz
        # Vaqtni intervalga oshiramiz (datetime yaratib qo'shish kerak)
        dt_temp = datetime.datetime.combine(datetime.date.today(), current_time) + interval
        current_time = dt_temp.time()
    return choices


class TimeChoiceField(forms.TimeField):
    """Select widget ishlatadigan TimeField."""

    def __init__(self, *args, **kwargs):
        choices = kwargs.pop("choices", [])
        super().__init__(*args, **kwargs)
        # Widget uchun tanlovlar (qiymat=time object, ko'rinish=string)
        self.widget = forms.Select(choices=choices)


# --- Ish Vaqti Uchun Maxsus Forma ---
class WorkingHoursInlineForm(forms.ModelForm):
    """Vaqt uchun Select widget ishlatadigan forma."""
    from_hour = TimeChoiceField(choices=time_choices(30), label=_("Boshlanish vaqti"))  # Intervalni o'zgartirish mumkin
    to_hour = TimeChoiceField(choices=time_choices(30), label=_("Tugash vaqti"))

    class Meta:
        model = WorkingHours
        fields = '__all__'

    # Qo'shimcha validatsiya (masalan, to_hour > from_hour)
    def clean(self):
        cleaned_data = super().clean()
        from_hour = cleaned_data.get("from_hour")
        to_hour = cleaned_data.get("to_hour")

        if from_hour and to_hour and from_hour >= to_hour:
            raise ValidationError(_("Tugash vaqti boshlanish vaqtidan keyin bo'lishi kerak."))
        return cleaned_data


class WorkingHoursDuplicateCheckFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        seen_combinations = set()
        forms_to_check = []

        for form in self.forms:
            # Faqat to'ldirilgan va o'chirishga belgilanmagan formalarni olamiz
            if form.has_changed() and not form.cleaned_data.get('DELETE', False):
                if form.cleaned_data.get('weekday') is not None and form.cleaned_data.get('from_hour') is not None:
                    forms_to_check.append(form)

        for form in forms_to_check:
            weekday = form.cleaned_data.get('weekday')
            from_hour = form.cleaned_data.get('from_hour')
            key = (weekday, from_hour)

            if key in seen_combinations:
                # Xatolikni 'from_hour' maydoniga qo'shamiz
                form.add_error('from_hour', ValidationError(
                    _("Bu filial uchun ushbu kunda bir xil boshlanish vaqti allaqachon kiritilgan yoki kiritilmoqda.")
                ))
            else:
                seen_combinations.add(key)


class WorkingHoursInline(admin.TabularInline):
    model = WorkingHours
    form = WorkingHoursInlineForm  # Vaqt tanlovchi forma
    formset = WorkingHoursDuplicateCheckFormSet  # Dublikat tekshiruvchi formset
    extra = 1  # Yangi qator qo'shish uchun
    # max_num olib tashlandi yoki kerak bo'lsa kattaroq qo'ying
    fields = ('weekday', 'from_hour', 'to_hour')


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'phone_number', 'is_active', 'avg_preparation_minutes')
    list_filter = ('is_active',)
    search_fields = ('name', 'address')
    inlines = [WorkingHoursInline]  # WorkingHours formasini shu yerga qo'shamiz


# OrderItem modelini Order adminida inline ko'rsatish uchun
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0  # Yangi item qo'shishga ruxsat bermaymiz (buyurtma yaratilganda qo'shiladi)
    # Inline formada ko'rinadigan maydonlar (o'zgartirib bo'lmaydigan qilamiz)
    fields = ('product', 'quantity', 'price_per_unit', 'total_price')
    readonly_fields = ('product', 'quantity', 'price_per_unit', 'total_price')

    # Yangi item qo'shish yoki o'chirishni taqiqlash
    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'delivery_type', 'total_price', 'pickup_branch', 'created_at')
    list_filter = ('status', 'delivery_type', 'created_at', 'pickup_branch')
    search_fields = ('id', 'user__username', 'user__phone_number', 'address')
    list_display_links = ('id', 'user')  # ID va User ustunlarini link qilamiz
    date_hierarchy = 'created_at'  # Sana bo'yicha tezkor navigatsiya
    inlines = [OrderItemInline]  # OrderItem'larni shu yerda ko'rsatamiz

    # Buyurtmani tahrirlash formasida ko'p maydonlarni faqat o'qish uchun qilamiz
    readonly_fields = (
        'user', 'total_price', 'created_at', 'updated_at',
        'estimated_ready_at', 'estimated_delivery_at'  # Bu maydonlar avtomatik hisoblanadi
        # Agar buyurtma statusini faqat API orqali o'zgartirmoqchi bo'lsak:
        # 'status', 'delivery_type', 'address', 'latitude', 'longitude',
        # 'payment_type', 'notes', 'pickup_branch'
    )

    # Agar statusni admindan o'zgartirish kerak bo'lsa, readonly_fields'dan 'status'ni olib tashlang

    # Buyurtma formasidagi maydonlarni guruhlash (ixtiyoriy)
    fieldsets = (
        (None, {
            'fields': ('user', 'status', 'total_price')
        }),
        ('Yetkazib Berish/Olib Ketish', {
            'fields': ('delivery_type', 'pickup_branch', 'address', 'latitude', 'longitude')
        }),
        ('To\'lov va Izohlar', {
            'fields': ('payment_type', 'notes')
        }),
        ('Taxminiy Vaqtlar', {
            'fields': ('estimated_ready_at', 'estimated_delivery_at')
        }),
        ('Sana', {
            'fields': ('created_at', 'updated_at')
        }),
    )
