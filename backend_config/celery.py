# backend_config/celery.py
import os
from celery import Celery

# Django settings modulini Celery uchun standart qilib belgilaymiz.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend_config.settings')

# Celery ilovasini yaratamiz (loyihangiz nomi bilan atashingiz mumkin)
app = Celery('backend_config')

# Sozlamalarni Django settings.py faylidan oladi, 'CELERY_' prefiksi bilan.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Django ilovalaridagi tasks.py fayllarini avtomatik topadi.
app.autodiscover_tasks()

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')