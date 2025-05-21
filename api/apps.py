from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'
    verbose_name = _("API Ma'lumotlari") # Buni o'zgartirgandik

    def ready(self):
        from . import signals
