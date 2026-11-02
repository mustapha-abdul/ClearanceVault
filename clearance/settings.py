
from pathlib import Path
import os

# BASE DIRECTORY
BASE_DIR = Path(__file__).resolve().parent.parent


# SECURITY SETTINGS
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-local-development-key")

DEBUG = False

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '.onrender.com']

CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com']


# APPLICATIONS
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Your application
    'jambapp',
]


# MIDDLEWARE
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# URL CONFIGURATION
ROOT_URLCONF = 'clearance.urls'


# TEMPLATES
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


# WSGI
WSGI_APPLICATION = 'clearance.wsgi.application'


# DATABASE - MYSQL 8.4
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'clearance'),
        'USER': os.environ.get('DB_USER', 'clearance_app'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '3307'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'ssl_mode': os.environ.get('DB_SSL_MODE', 'PREFERRED'),
        },
    }
}
# PASSWORD VALIDATION
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


# INTERNATIONALIZATION
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Africa/Lagos'

USE_I18N = True

USE_TZ = True


# STATIC FILES
STATIC_URL = 'static/'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

STATIC_ROOT = BASE_DIR / 'staticfiles'


# DEFAULT PRIMARY KEY
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# GMAIL EMAIL CONFIGURATION - DJANGO 6.1
MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
        'OPTIONS': {
            'host': 'smtp.gmail.com',
            'port': 587,
            'username': 'abdulhakeemmustapha337@gmail.com',
            'password': os.environ.get("EMAIL_HOST_PASSWORD", ""),
            'use_tls': True,
            'timeout': 20,
        },
    },
}

DEFAULT_FROM_EMAIL = 'abdulhakeemmustapha337@gmail.com'

# =====================================================
# PAYSTACK PAYMENT CONFIGURATION
# =====================================================

PAYSTACK_SECRET_KEY = os.environ.get("PAYSTACK_SECRET_KEY", "")

PAYSTACK_PLUS_PLAN_CODE = os.environ.get(
    "PAYSTACK_PLUS_PLAN_CODE",
    ""
)

PAYSTACK_PRO_PLAN_CODE = os.environ.get(
    "PAYSTACK_PRO_PLAN_CODE",
    ""
)

PAYSTACK_PLAN_CODES = {
    "plus": PAYSTACK_PLUS_PLAN_CODE,
    "pro": PAYSTACK_PRO_PLAN_CODE,
}

# Amounts are in kobo: ₦1,000 = 100,000 kobo
PAYSTACK_PLAN_AMOUNTS = {
    "plus": 100000,
    "pro": 200000,
}

PAYSTACK_BASE_URL = "https://api.paystack.co"
PAYSTACK_TIMEOUT = 30

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}