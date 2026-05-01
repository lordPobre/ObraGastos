"""
settings.py — Producción para Railway

Variables de entorno requeridas en Railway:
  SECRET_KEY        → clave secreta Django (genera una nueva)
  DATABASE_URL      → se inyecta automáticamente por Railway PostgreSQL
  ALLOWED_HOSTS     → tu dominio Railway, ej: obragastos.up.railway.app
  R2_BUCKET_NAME    → nombre del bucket Cloudflare R2
  R2_ACCOUNT_ID     → ID de cuenta Cloudflare
  R2_ACCESS_KEY     → Access Key ID de R2
  R2_SECRET_KEY     → Secret Access Key de R2
  R2_CUSTOM_DOMAIN  → dominio público del bucket (opcional)
  MS_CLIENT_ID      → credenciales SharePoint (igual que antes)
  MS_TENANT_ID
  MS_CLIENT_SECRET
  MS_SITE_ID
"""
from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# ─── SEGURIDAD ────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ['SECRET_KEY']
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')
CSRF_TRUSTED_ORIGINS = [f'https://{h}' for h in ALLOWED_HOSTS if h]

# ─── APPS ─────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'storages',
    'gastos',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # archivos estáticos en producción
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'core.wsgi.application'

# ─── BASE DE DATOS (PostgreSQL vía Railway) ───────────────────────────────────
DATABASES = {
    'default': dj_database_url.config(
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ─── ARCHIVOS ESTÁTICOS (WhiteNoise) ─────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ─── ARCHIVOS MEDIA (Cloudflare R2) ──────────────────────────────────────────
# R2 es compatible con la API de S3, por eso usamos django-storages con S3
R2_BUCKET_NAME   = os.getenv('R2_BUCKET_NAME', '')
R2_ACCOUNT_ID    = os.getenv('R2_ACCOUNT_ID', '')
R2_ACCESS_KEY    = os.getenv('R2_ACCESS_KEY', '')
R2_SECRET_KEY    = os.getenv('R2_SECRET_KEY', '')
R2_CUSTOM_DOMAIN = os.getenv('R2_CUSTOM_DOMAIN', '')

if R2_BUCKET_NAME:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_STORAGE_BUCKET_NAME = R2_BUCKET_NAME
    AWS_ACCESS_KEY_ID = R2_ACCESS_KEY
    AWS_SECRET_ACCESS_KEY = R2_SECRET_KEY
    AWS_S3_ENDPOINT_URL = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com'
    AWS_S3_CUSTOM_DOMAIN = R2_CUSTOM_DOMAIN or None
    AWS_DEFAULT_ACL = 'public-read'
    AWS_S3_FILE_OVERWRITE = False
    MEDIA_URL = f'https://{R2_CUSTOM_DOMAIN}/' if R2_CUSTOM_DOMAIN else f'{AWS_S3_ENDPOINT_URL}/{R2_BUCKET_NAME}/'
else:
    # Fallback local si no hay R2 configurado
    MEDIA_URL = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# ─── TESSERACT ────────────────────────────────────────────────────────────────
# En Railway, Tesseract se instala vía nixpacks.toml en /usr/bin/tesseract
TESSERACT_CMD = os.getenv('TESSERACT_CMD', '/usr/bin/tesseract')

# ─── INTERNACIONALIZACIÓN ─────────────────────────────────────────────────────
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# ─── AUTH ─────────────────────────────────────────────────────────────────────
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
LOGIN_URL = '/accounts/login/'

# ─── PASSWORDS ────────────────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

X_FRAME_OPTIONS = 'SAMEORIGIN'

# ─── SHAREPOINT ───────────────────────────────────────────────────────────────
MS_CLIENT_ID     = os.getenv('MS_CLIENT_ID')
MS_TENANT_ID     = os.getenv('MS_TENANT_ID')
MS_CLIENT_SECRET = os.getenv('MS_CLIENT_SECRET')
MS_SITE_ID       = os.getenv('MS_SITE_ID')

# ─── LOGGING ──────────────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'gastos': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
