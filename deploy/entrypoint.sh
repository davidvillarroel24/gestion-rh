#!/bin/sh
# Aplica migraciones pendientes y arranca el comando del contenedor
# (gunicorn en el VPS, runserver en local).
set -e

python manage.py migrate --noinput

exec "$@"
