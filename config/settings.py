"""
Django settings for the Dav Doner Club project.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')


def _environment_flag(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise ImproperlyConfigured(f'{name} must be a boolean value.')


SECRET_KEY = 'django-insecure-$$ikl*g^7)j#5%$ik+2#g8gy&rihox$+%^34qe34f)#dpmwcjb'

DEBUG = True

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'pages',
    'menu',
    'orders',
    'accounts',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.template.context_processors.media',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'menu.context_processors.categories',
                'orders.context_processors.cart',
                'pages.context_processors.site_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'ru-ru'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'accounts:profile'
LOGOUT_REDIRECT_URL = 'pages:home'

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Прибавлять к общему резюме заказа столько, сколько нужно для бесплатной доставки.
CART_SESSION_KEY = 'cart'

TOCHKA_ENABLED = _environment_flag('TOCHKA_ENABLED', False)
TOCHKA_SANDBOX = _environment_flag('TOCHKA_SANDBOX', True)
TOCHKA_API_BASE_URL = (
    'https://enter.tochka.com/sandbox/v2'
    if TOCHKA_SANDBOX else 'https://enter.tochka.com/uapi'
)
TOCHKA_JWT_TOKEN = os.environ.get('TOCHKA_JWT_TOKEN') or os.environ.get('T_TOKEN', '')
TOCHKA_CLIENT_ID = os.environ.get('TOCHKA_CLIENT_ID') or os.environ.get('T_CLIENT_ID', '')
TOCHKA_CUSTOMER_CODE = os.environ.get('TOCHKA_CUSTOMER_CODE') or (
    '1234567ab' if TOCHKA_SANDBOX else ''
)
TOCHKA_MERCHANT_ID = os.environ.get('TOCHKA_MERCHANT_ID', '')
TOCHKA_WEBHOOK_URL = os.environ.get('TOCHKA_WEBHOOK_URL', '')
TOCHKA_SUCCESS_URL = os.environ.get('TOCHKA_SUCCESS_URL', '')
TOCHKA_FAIL_URL = os.environ.get('TOCHKA_FAIL_URL', '')
TOCHKA_WEBHOOK_JWK = os.environ.get('TOCHKA_WEBHOOK_JWK', '')
TOCHKA_WEBHOOK_CLAIMS_CONFIRMED = True
TOCHKA_PAYMENT_MODES = [
    mode.strip()
    for mode in os.environ.get('TOCHKA_PAYMENT_MODES', 'card,sbp').split(',')
    if mode.strip()
]
TOCHKA_PAYMENT_TTL_MINUTES = os.environ.get('TOCHKA_PAYMENT_TTL_MINUTES', '')
TOCHKA_FISCALIZATION_ENABLED = _environment_flag(
    'TOCHKA_FISCALIZATION_ENABLED',
    False,
)
TOCHKA_TAX_SYSTEM_CODE = os.environ.get('TOCHKA_TAX_SYSTEM_CODE', '')
TOCHKA_VAT_TYPE = os.environ.get('TOCHKA_VAT_TYPE', '')
TOCHKA_PAYMENT_METHOD = os.environ.get('TOCHKA_PAYMENT_METHOD', '')
TOCHKA_PAYMENT_OBJECT = os.environ.get('TOCHKA_PAYMENT_OBJECT', '')
TOCHKA_DELIVERY_VAT_TYPE = os.environ.get('TOCHKA_DELIVERY_VAT_TYPE', '')
TOCHKA_DELIVERY_PAYMENT_OBJECT = os.environ.get('TOCHKA_DELIVERY_PAYMENT_OBJECT', '')
PAYMENT_GATEWAY = (
    os.environ.get('PAYMENT_GATEWAY') or 'orders.tochka_gateway.TochkaPaymentGateway'
    if TOCHKA_ENABLED and TOCHKA_WEBHOOK_CLAIMS_CONFIRMED else ''
)
PAYMENT_CURRENCY = 'RUB'
