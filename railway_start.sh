#!/bin/bash
# railway_start.sh — se ejecuta en cada deploy antes de levantar el servidor

set -e  # detener si algo falla

echo "=== Aplicando migraciones ==="
python manage.py migrate --noinput

echo "=== Recolectando archivos estáticos ==="
python manage.py collectstatic --noinput

echo "=== Iniciando servidor ==="
gunicorn core.wsgi:application \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --timeout 120 \
    --log-level info
