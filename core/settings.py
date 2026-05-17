"""
Perseus Control v4 — settings.py
Multitenant · Railway/Render ready · python-decouple
"""
from pathlib import Path
from decouple import config, Csv
import dj_database_url
import os

# ── Rutas ─────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

# ── GTK Windows (WeasyPrint) ──────────────────────────────────
if os.name == 'nt':
    _GTK = r'C:\Program Files\GTK3-Runtime Win64\bin'
    if os.path.exists(_GTK):
        try:
            os.add_dll_directory(_GTK)
            os.environ['PATH'] = _GTK + ';' + os.environ.get('PATH', '')
        except OSError:
            pass

# ── Seguridad ─────────────────────────────────────────────────
SECRET_KEY    = config('SECRET_KEY', default='django-insecure-build-placeholder-key-not-for-production')
DEBUG         = config('DEBUG', default=False, cast=bool)
ENVIRONMENT   = config('ENVIRONMENT', default='production')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*', cast=Csv())
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())

# ── Apps ──────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'storages',
    'django_celery_beat',
    'apps.asistencia',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Estáticos en producción
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Middleware de empresa activa (multitenant)
    'apps.asistencia.middleware.EmpresaActivaMiddleware',
]

ROOT_URLCONF   = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS':    [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # Inyecta empresa activa en todos los templates
                'apps.asistencia.context_processors.empresa_activa',
            ],
        },
    },
]

_DATABASE_URL = config('DATABASE_URL', default='')

if _DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            _DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME':   BASE_DIR / 'db.sqlite3',
        }
    }

# ── Contraseñas ───────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── Internacionalización ──────────────────────────────────────
LANGUAGE_CODE = 'es-cl'
TIME_ZONE     = 'America/Santiago'
USE_I18N      = True
USE_TZ        = True

STATIC_URL   = '/static/'
STATIC_ROOT  = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

AWS_ACCESS_KEY_ID      = config('AWS_ACCESS_KEY_ID',      default='')
AWS_SECRET_ACCESS_KEY  = config('AWS_SECRET_ACCESS_KEY',  default='')
AWS_STORAGE_BUCKET_NAME= config('AWS_STORAGE_BUCKET_NAME',default='')
AWS_S3_REGION_NAME     = config('AWS_S3_REGION_NAME',     default='sa-east-1')

if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_STORAGE_BUCKET_NAME:
    DEFAULT_FILE_STORAGE  = 'storages.backends.s3boto3.S3Boto3Storage'
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL       = 'public-read'
    AWS_QUERYSTRING_AUTH  = False
    AWS_S3_CUSTOM_DOMAIN  = f'{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com'
    MEDIA_URL             = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
else:
    MEDIA_URL  = '/media/'
    MEDIA_ROOT = BASE_DIR / 'media'

# ── Autenticación ─────────────────────────────────────────────
LOGIN_URL           = 'login'
LOGIN_REDIRECT_URL  = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# ── Email ─────────────────────────────────────────────────────
if ENVIRONMENT == 'development' and DEBUG:
    # En desarrollo: imprimir emails en consola
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST          = 'smtp.gmail.com'
    EMAIL_PORT          = 587
    EMAIL_USE_TLS       = True
    EMAIL_HOST_USER     = config('EMAIL_HOST_USER',     default='')
    EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
    DEFAULT_FROM_EMAIL  = config(
        'DEFAULT_FROM_EMAIL',
        default=f'Perseus Control <{config("EMAIL_HOST_USER", default="")}>'
    )

# ── IA Gemini ─────────────────────────────────────────────────
GEMINI_API_KEY = config('GEMINI_API_KEY', default='')

# ── Seguridad en producción ───────────────────────────────────
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER       = True
    SECURE_CONTENT_TYPE_NOSNIFF     = True
    X_FRAME_OPTIONS                  = 'DENY'
    SECURE_HSTS_SECONDS              = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS   = True
    SESSION_COOKIE_SECURE            = True
    CSRF_COOKIE_SECURE               = True

# ── Misc ──────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Celery + Redis ────────────────────────────────────────────
REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')

CELERY_BROKER_URL       = REDIS_URL
CELERY_RESULT_BACKEND   = REDIS_URL
CELERY_TIMEZONE         = TIME_ZONE
CELERY_ACCEPT_CONTENT   = ['json']
CELERY_TASK_SERIALIZER  = 'json'
CELERY_RESULT_SERIALIZER= 'json'

# SSL para Upstash Redis (rediss://)
if REDIS_URL.startswith('rediss://'):
    import ssl
    _ssl = {'ssl_cert_reqs': ssl.CERT_NONE}
    CELERY_BROKER_USE_SSL        = _ssl
    CELERY_REDIS_BACKEND_USE_SSL = _ssl
CELERY_TIMEZONE         = TIME_ZONE  # America/Santiago
CELERY_ACCEPT_CONTENT   = ['json']
CELERY_TASK_SERIALIZER  = 'json'
CELERY_RESULT_SERIALIZER= 'json'

# Prevenir que las tareas queden colgadas
CELERY_TASK_TIME_LIMIT       = 300   # 5 minutos máximo por tarea
CELERY_TASK_SOFT_TIME_LIMIT  = 240

# django-celery-beat guarda el schedule en la base de datos
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# ── Logging básico ────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO' if DEBUG else 'WARNING',
            'propagate': False,
        },
        'apps.asistencia': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}