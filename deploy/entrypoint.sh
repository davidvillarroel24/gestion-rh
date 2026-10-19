#!/bin/sh
# Aplica migraciones pendientes y arranca el comando del contenedor
# (gunicorn en el VPS, runserver en local).
set -e

python manage.py migrate --noinput
# Primera vez: carga municipios/provincias/regiones (no hace nada si ya existen).
python manage.py cargar_limites --si-vacio

exec "$@"
