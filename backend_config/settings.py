"""
Django settings for backend_config project.

Generated by 'django-admin startproject' using Django 4.2.20.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

import os
from dotenv import load_dotenv
from datetime import timedelta
from pathlib import Path
from django.utils.translation import gettext_lazy as _

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(os.path.join(BASE_DIR, '.env'))
GOOGLE_DRIVE_CREDENTIALS_JSON_PATH = os.path.join(BASE_DIR, 'credentials.json')
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-v$=*ebwskt^8d07kh0&55v!=9&x4&5w*wuna^^gpa18o-ne%g8'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    # Qo'shilgan kutubxonalar
    'debug_toolbar',
    'rest_framework',
    'rest_framework_simplejwt',
    'parler',
    # O'zimizning ilova
    'api.apps.ApiConfig',
]

AUTH_USER_MODEL = 'api.User'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.middleware.common.CommonMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.locale.LocaleMiddleware',
]

ROOT_URLCONF = 'backend_config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend_config.wsgi.application'

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT'),
    }
}

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'uz'  # Standart til (agar til aniqlanmasa)

# Qo'llab-quvvatlanadigan tillar ro'yxati
LANGUAGES = [
    ('uz', _('Uzbek')),
    ('ru', _('Russian')),
]

TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# django-parler sozlamalari
PARLER_LANGUAGES = {
    None: (
        {'code': 'uz', },  # O'zbek tili
        {'code': 'ru', },  # Rus tili
    ),
    'default': {
        'fallback': 'uz',  # Agar joriy tilda tarjima bo'lmasa, qaysi tilga qaytish kerak
        'hide_untranslated': False,  # Tarjima qilinmagan obyektlarni yashirish/ko'rsatish
    }
}

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Django REST Framework sozlamalari
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
        # Ko'rish uchun ruxsat, o'zgartirish uchun login talab qiladi
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10
}

# Simple JWT sozlamalari
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=350),  # Access token yashash muddati (masalan, 1 soat)
    'REFRESH_TOKEN_LIFETIME': timedelta(days=355),  # Refresh token yashash muddati (masalan, 1 kun)
    # Boshqa sozlamalar...
}

# CORS Sozlamalari
# Ishlab chiqish (development) uchun hammaga ruxsat berish (keyinroq aniq domenlarga o'zgartiring)
CORS_ALLOW_ALL_ORIGINS = True
# Yoki aniqroq:
# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:8080", # Agar local test serveringiz shu portda bo'lsa
#     "http://127.0.0.1:8080",
#     # Keyinchalik Mini App hosting qilinadigan manzil(lar)
# ]
# CORS_ALLOW_CREDENTIALS = True # Agar cookie yoki authorization header kerak bo'lsa

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

INTERNAL_IPS = [
    "127.0.0.1",
]
