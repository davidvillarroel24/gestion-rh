"""
Configuración de Gestión RH (SDMAyRH).

Todo lo que cambia entre la PC y el VPS viene de variables de entorno
(deploy/.env + docker-compose); no hay archivos de settings separados.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def cargar_env(ruta):
    """Lee deploy/.env al correr fuera de Docker (en Docker lo inyecta compose).
    No pisa variables que ya estén definidas en el entorno."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip("\"'"))


cargar_env(BASE_DIR.parent / "deploy" / ".env")


def env_list(nombre, por_defecto=""):
    return [v.strip() for v in os.environ.get(nombre, por_defecto).split(",") if v.strip()]


DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("Falta DJANGO_SECRET_KEY (ver deploy/.env.example).")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "simple_history",
    "core",
    "territorio",
    "proyectos",
    "visor",
    "importador",
    "reportes",
]

# Usuario propio (con unidades y municipios asignados). Definido desde el inicio:
# Django no permite cambiarlo después sin rehacer la base.
AUTH_USER_MODEL = "core.Usuario"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Auditoría: registra qué usuario hizo cada cambio.
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": os.environ.get("POSTGRES_DB", "gestionrh"),
        "USER": os.environ.get("POSTGRES_USER", "gestionrh"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "America/La_Paz"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Documentos subidos. No se sirven como estáticos públicos: se descargan
# a través de una vista de Django que verifica permisos.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# En Docker las librerías se encuentran solas. Solo hace falta indicarlas
# si se corre Django fuera de Docker (ej. Windows con las DLL de QGIS).
if os.environ.get("GDAL_LIBRARY_PATH"):
    GDAL_LIBRARY_PATH = os.environ["GDAL_LIBRARY_PATH"]
    # Usar también los datos de PROJ/GDAL de esa misma instalación. Si no, gana lo
    # que haya dejado otro programa en las variables globales (el instalador de
    # PostGIS para Windows deja PROJ_LIB con un proj.db más viejo -> "OGR failure").
    _raiz = Path(GDAL_LIBRARY_PATH).resolve().parents[1]
    for _variables, _carpeta in (
        (("PROJ_DATA", "PROJ_LIB"), _raiz / "share" / "proj"),
        (("GDAL_DATA",), _raiz / "apps" / "gdal" / "share" / "gdal"),
    ):
        if _carpeta.is_dir():
            for _variable in _variables:
                os.environ[_variable] = str(_carpeta)
if os.environ.get("GEOS_LIBRARY_PATH"):
    GEOS_LIBRARY_PATH = os.environ["GEOS_LIBRARY_PATH"]

# Mapas base del visor (D19: gratuitos). Para cambiar de proveedor se edita esta
# lista; el primero es el predeterminado. Respetar la política de uso de cada uno.
MAPAS_BASE = [
    {"id": "osm", "nombre": "OpenStreetMap", "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
     "atribucion": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>', "max_zoom": 19},
    {"id": "topo", "nombre": "Relieve (OpenTopoMap)", "url": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
     "atribucion": '&copy; OpenStreetMap, SRTM | &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
     "max_zoom": 17},
    {"id": "claro", "nombre": "Claro (CARTO)", "url": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
     "atribucion": '&copy; OpenStreetMap &copy; <a href="https://carto.com/attributions">CARTO</a>', "max_zoom": 20},
    {"id": "oscuro", "nombre": "Oscuro (CARTO)", "url": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
     "atribucion": '&copy; OpenStreetMap &copy; <a href="https://carto.com/attributions">CARTO</a>', "max_zoom": 20},
    {"id": "satelite", "nombre": "Satélite (Esri)",
     "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
     "atribucion": "Tiles &copy; Esri", "max_zoom": 19},
]

LOGIN_URL = "core:ingresar"
LOGIN_REDIRECT_URL = "visor:visor"
LOGOUT_REDIRECT_URL = "core:ingresar"

# OpenStreetMap bloquea los mosaicos pedidos sin cabecera Referer ("Access blocked").
# Django usa "same-origin" por defecto, que no la envía a otros sitios; con este
# valor (el estándar de los navegadores) se envía solo el dominio, nunca la ruta.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Detrás del proxy compartido (Caddy termina el HTTPS y avisa con X-Forwarded-Proto).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
