import os
import ssl
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('perseus')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
app.autodiscover_tasks(['apps.asistencia'])

# SSL para Upstash Redis (rediss://)
REDIS_URL = os.environ.get('REDIS_URL', '')
if REDIS_URL.startswith('rediss://'):
    ssl_options = {'ssl_cert_reqs': ssl.CERT_NONE}
    app.conf.broker_use_ssl        = ssl_options
    app.conf.redis_backend_use_ssl = ssl_options

# Schedule de tareas
app.conf.beat_schedule = {
    'revisar-ausencias': {
        'task':     'apps.asistencia.tasks.revisar_ausencias',
        'schedule': crontab(minute='*/30', hour='7-20', day_of_week='1-5'),
    },
    'revisar-exceso-jornada': {
        'task':     'apps.asistencia.tasks.revisar_exceso_jornada',
        'schedule': crontab(minute='*/30', hour='7-22', day_of_week='1-6'),
    },
    'limpiar-logs-alertas': {
        'task':     'apps.asistencia.tasks.limpiar_logs_alertas',
        'schedule': crontab(hour=2, minute=0),
    },
}
