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
    User, Category, Product, Branch, WorkingHours, Order, OrderItem, Promotion
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


@admin.register(Category)
class CategoryAdmin(TranslatableAdmin):
    list_display = ('id', '_display_translated_name', 'slug', 'parent', 'order', 'is_active')
    list_filter = ('is_active', 'parent', 'translations__language_code')
    search_fields = ('translations__name', 'translations__slug')

    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'image', 'parent', 'order', 'is_active')
        }),
        # Agar Google Drive maydonlarini admin panelida (faqat o'qish uchun) ko'rsatmoqchi bo'lsangiz:
        # (_('Google Drive Ma\'lumotlari'), {
        #     'fields': ('google_drive_file_id', 'image_gdrive_url'),
        #     'classes': ('collapse',), # Boshida yopiq turadi
        #     'description': _("Bu maydonlar avtomatik to'ldiriladi va tahrirlanmaydi.")
        # }),
    )

    # readonly_fields = ('google_drive_file_id', 'image_gdrive_url') # Agar fieldsetsda bo'lsa

    def get_prepopulated_fields(self, request, obj=None):
        # Parler har bir til uchun alohida slug generatsiya qilishi mumkin
        # Yoki faqat asosiy til uchun sozlash mumkin. Hozircha standart qoldiramiz.
        return {'slug': ('name',)}

    def _display_translated_name(self, obj):
        return obj.safe_translation_getter("name", any_language=True, default=f"Category ID: {obj.pk}")

    _display_translated_name.short_description = _("Nomi (Tarjima)")
    _display_translated_name.admin_order_field = 'translations__name'

    def get_queryset(self, request):
        # TranslatableAdmin standart querysetini olamiz
        qs = super().get_queryset(request)
        # Dublikatlarni oldini olish uchun .distinct() qo'shamiz
        return qs.distinct()  # <-- BU QATORNI QO'SHING


# ProductAdmin'ni TranslatableAdmin'ga qaytaramiz va sozlamalarni tiklaymiz
@admin.register(Product)
class ProductAdmin(TranslatableAdmin):  # <-- TranslatableAdmin'dan meros olamiz
    list_display = ('name', 'category', 'price', 'is_available')  # <-- 'name'ni qaytaramiz
    list_filter = ('category', 'is_available')
    search_fields = ('translations__name', 'translations__description', 'category__translations__name')
    list_editable = ('price', 'is_available')


# WorkingHours modelini Branch adminida inline ko'rsatish uchun
def time_choices(interval_minutes=30):
    """Generates time choices with specified interval using minutes, includes 23:59."""
    choices = []
    start_minutes = 0  # 00:00
    # Iterate up to but NOT including 24*60 (midnight of next day)
    total_minutes_in_day = 24 * 60

    current_minutes = start_minutes
    while current_minutes < total_minutes_in_day:
        hours = current_minutes // 60
        minutes = current_minutes % 60
        # Handle potential errors if hours exceed 23 (shouldn't with < total_minutes_in_day)
        try:
            current_time = time(hours, minutes)
            time_str = current_time.strftime("%H:%M")
            choices.append((current_time, time_str))
        except ValueError:
            # Should not happen with current logic, but as a safeguard
            pass

            # Increment minutes
        current_minutes += interval_minutes

    # Add 23:59 specifically if not already the last interval step
    time_2359 = time(23, 59)
    if not choices or choices[-1][0] != time_2359:
        # Ensure 23:59 wasn't naturally generated if interval=1
        if time_2359 not in [t[0] for t in choices]:
            choices.append((time_2359, "23:59"))

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


@admin.register(Promotion)
class PromotionAdmin(TranslatableAdmin):  # <-- TranslatableAdmin dan meros olamiz
    list_display = ('title', 'start_date', 'end_date', 'is_active', 'is_currently_active_display')
    list_filter = ('is_active', 'start_date', 'end_date')
    search_fields = ('translations__title', 'translations__description')  # Tarjimalar orqali qidirish

    # TranslatableAdmin o'zi tarjima maydonlarini to'g'ri chiqaradi,
    # shuning uchun 'fields' yoki 'fieldsets' ni maxsus ko'rsatish shart emas (agar standart ko'rinish qoniqtirsa)
    # Agar fieldslarni tartiblamoqchi bo'lsangiz:
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'image')  # title va description parler tomonidan tab qilinadi
        }),
        (_('Amal qilish muddati va statusi'), {
            'fields': ('start_date', 'end_date', 'is_active')
        }),
    )

    def is_currently_active_display(self, obj):
        return obj.is_currently_active

    is_currently_active_display.boolean = True
    is_currently_active_display.short_description = _("Hozir Aktivmi?")
