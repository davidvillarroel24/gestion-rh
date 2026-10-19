# Gestión RH — SDMAyRH

Sistema de gestión y seguimiento de proyectos de la Secretaría Departamental de Medio Ambiente y Recursos Hídricos (Gobernación de Cochabamba).

**Stack**: Django 5.2 + GeoDjango · PostgreSQL 17 + PostGIS 3.5 · Docker · dominio **https://gestion-rh.duckdns.org**

> El diseño completo (modelo de datos, decisiones, plan por fases) vive en el documento de diseño del proyecto (`README.md` de la carpeta superior, fuera de este repositorio).

## Estructura

```
gestion-rh/
├─ Dockerfile                    imagen de la app (Python 3.12 + GDAL/GEOS/PROJ)
├─ requirements.txt              dependencias con versión exacta
├─ deploy/
│  ├─ docker-compose.yml         VPS (detrás del proxy compartido)
│  ├─ docker-compose.local.yml   ajustes para desarrollo en la PC
│  ├─ .env.example               variables (copiar a .env)
│  └─ entrypoint.sh              aplica migraciones al arrancar
└─ src/                          proyecto Django
   ├─ config/                    settings, urls, wsgi
   ├─ core/                      núcleo (inicio, /salud/)
   ├─ templates/  static/
   └─ manage.py
```

## Desarrollo en la PC

Requiere **Docker Desktop**.

```bash
cd deploy
cp .env.example .env          # completar contraseñas y DJANGO_SECRET_KEY
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

- App: http://localhost:8000 (recarga sola al guardar cambios en `src/`).
- Estado: http://localhost:8000/salud/ → `{"estado": "ok", "postgis": "..."}`
- Base de datos desde QGIS: host `localhost`, puerto **5433**, base/usuario/contraseña de `.env`.

Primer administrador (en otra terminal, dentro de `deploy/`):

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec web python manage.py createsuperuser
```

Crear migraciones después de cambiar modelos:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml exec web python manage.py makemigrations
```

Empezar la base de cero (**borra todos los datos**):

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml down -v
```

## Despliegue en el VPS compartido (Contabo)

El VPS lo comparten varios proyectos. **Solo el proxy compartido** (Caddy en `/srv/proxy`) usa los puertos 80/443: este stack no publica puertos, se conecta a la red `proxy` y declara su dominio con las etiquetas `caddy` del servicio `web`. La base de datos queda en la red interna `interna`, sin acceso desde afuera ni desde otros proyectos. Cada contenedor tiene límite de memoria y CPU.

1. **DuckDNS**: apuntar `gestion-rh` a la IP del VPS (la IP es fija, no hace falta el script de actualización).
2. **Clonar** (llave de despliegue de solo lectura, igual que los otros proyectos):

   ```bash
   git clone git@github.com:<usuario>/<repositorio>.git /srv/gestion-rh
   ```

3. **Configurar**:

   ```bash
   cd /srv/gestion-rh/deploy
   cp .env.example .env
   nano .env        # secretos con: openssl rand -hex 32 ; DJANGO_DEBUG=0
   ```

4. **Levantar**:

   ```bash
   docker compose up -d --build
   docker compose exec web python manage.py createsuperuser
   ```

   El proxy compartido obtiene el certificado HTTPS en menos de un minuto → https://gestion-rh.duckdns.org

### Operación

```bash
cd /srv/gestion-rh/deploy
docker compose ps                  # estado (web debe figurar "healthy")
docker compose logs -f web         # logs de la app
git pull && docker compose up -d --build   # actualizar
docker stats                       # consumo (el VPS es compartido)
```

### Respaldos

El respaldo automático diario es un **avance futuro**. Mientras tanto, antes de cualquier cambio delicado (importaciones grandes, actualización de límites, cambios de modelo):

```bash
docker compose exec -T db pg_dump -U gestionrh -d gestionrh | gzip > respaldo-$(date +%F).sql.gz
```

Restaurar:

```bash
gunzip -c respaldo-AAAA-MM-DD.sql.gz | docker compose exec -T db psql -U gestionrh -d gestionrh
```

Los documentos subidos viven en el volumen `gestion-rh_media`.
