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
│  └─ entrypoint.sh              migra y carga los límites la primera vez
├─ herramientas/
│  └─ preparar_municipios.py     shp originales → src/territorio/datos/municipios.geojson (uso único)
└─ src/                          proyecto Django
   ├─ config/                    settings, urls, wsgi
   ├─ core/                      núcleo (inicio, /salud/)
   ├─ territorio/                regiones, provincias, municipios (+ datos/municipios.geojson)
   ├─ templates/  static/
   └─ manage.py
```

## Límites territoriales

- Fuente única: **48 municipios** (47 + TIOC Raqaypampa) en `src/territorio/datos/municipios.geojson`, EPSG:4326, ya corregidos (ver docstring de `herramientas/preparar_municipios.py`).
- Provincias (16) y regiones (5) guardan una geometría **derivada** de sus municipios; el departamento se calcula al vuelo. No se editan a mano.
- Carga: `python manage.py cargar_limites` (en Docker lo hace el entrypoint la primera vez, con `--si-vacio`). Volver a correrlo actualiza sin duplicar.
- API GeoJSON, simplificada según el zoom del mapa:
  `/territorio/municipios.geojson?z=10` · `/territorio/provincias.geojson` · `/territorio/regiones.geojson` · `/territorio/departamento.geojson`

## Desarrollo en la PC sin Docker (PostgreSQL local)

Requiere PostgreSQL 17 con **PostGIS** y QGIS instalado (Django usa su GDAL). `deploy/.env` ya trae `DB_HOST=localhost`, `DB_PORT=5433` y las rutas a las DLL de QGIS.

Base de datos (una vez, como `postgres`):

```sql
CREATE ROLE gestionrh LOGIN PASSWORD '<POSTGRES_PASSWORD del .env>';
CREATE DATABASE gestionrh OWNER gestionrh;
\c gestionrh
CREATE EXTENSION postgis;
```

Desde `gestion-rh/` (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
cd src
..\.venv\Scripts\python manage.py migrate
..\.venv\Scripts\python manage.py cargar_limites
..\.venv\Scripts\python manage.py createsuperuser
..\.venv\Scripts\python manage.py runserver
```

## Desarrollo en la PC con Docker

Requiere **Docker Desktop**.

```bash
cd deploy
cp .env.example .env          # completar contraseñas y DJANGO_SECRET_KEY
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

- App: http://localhost:8000 (recarga sola al guardar cambios en `src/`).
- Estado: http://localhost:8000/salud/ → `{"estado": "ok", "postgis": "..."}`
- Base de datos desde QGIS: host `localhost`, puerto **5434**, base/usuario/contraseña de `.env`.

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

## Usuarios, roles y alcance

- Login en `/ingresar/`. Los usuarios se crean en **Administración → Usuarios**.
- **Rol = grupo**: Administrador, Técnico de unidad, Encargado municipal, Funcionario de licencias, Consulta. Sus permisos están en `src/core/roles.py` y se aplican solos después de cada `migrate`.
- **Alcance**: al técnico se le asignan *unidades*; al encargado municipal, *municipios*. `core/alcance.py` filtra todo lo que cada uno ve.
- Para entrar a la Administración el usuario además necesita **«Staff»** marcado.
- Catálogos: no se precargan (solo unidades y tipos de fuente); se crean al usarlos y el sistema avisa si el nombre se parece a uno existente.

## Pruebas

```powershell
cd src
..\.venv\Scripts\python manage.py test
```

(Necesitan permiso para crear una base de prueba con PostGIS; en Docker funcionan directo.)

## Despliegue en el VPS compartido (Contabo)

El VPS lo comparten varios proyectos. **Solo el proxy compartido** (Caddy en `/srv/proxy`) usa los puertos 80/443: este stack no publica puertos, se conecta a la red `proxy` y declara su dominio con las etiquetas `caddy` del servicio `web`. La base de datos queda en la red interna `interna`, sin acceso desde afuera ni desde otros proyectos. Cada contenedor tiene límite de memoria y CPU.

Pasos probados en este VPS (mismo flujo que funcionó con los otros proyectos), como `root` por PuTTY. **Pegar cada comando en una sola línea**: PuTTY puede romper los `\` de continuación.

1. **DuckDNS**: apuntar `gestion-rh` a la IP del VPS. Comprobar: `nslookup gestion-rh.duckdns.org` debe devolver esa IP.
2. **Deploy key** (solo lectura, una por proyecto):

   ```bash
   ssh-keygen -t ed25519 -f /root/.ssh/github_gestionrh -N ""
   cat /root/.ssh/github_gestionrh.pub
   ```

   GitHub → repositorio → **Settings → Deploy keys → Add deploy key**, pegar la línea, **sin** "Allow write access".
3. **Clonar** y dejar la llave guardada en la config **local** del repositorio (así `git pull` funciona siempre sin prefijo; no usar `/root/.ssh/config`, que es global y choca con las llaves de los otros proyectos):

   ```bash
   GIT_SSH_COMMAND="ssh -i /root/.ssh/github_gestionrh -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new" git clone git@github.com:<usuario>/<repositorio>.git /srv/gestion-rh
   cd /srv/gestion-rh
   git config --local core.sshCommand "ssh -i /root/.ssh/github_gestionrh -o IdentitiesOnly=yes"
   git config --local --get core.sshCommand
   ```

4. **Configurar** (`openssl rand -hex 32` dos veces: contraseña de la base y clave de Django):

   ```bash
   cd /srv/gestion-rh/deploy
   cp .env.example .env
   nano .env
   ```

   `DOMINIO=gestion-rh.duckdns.org`, `DJANGO_DEBUG=0`. **No** copiar las líneas de Windows (`DB_HOST`, `GDAL_LIBRARY_PATH`…) del `.env` de la PC.
5. **Levantar** (la primera vez tarda unos minutos: instala GDAL; migra y carga los 48 municipios sola):

   ```bash
   docker compose up -d --build
   docker compose ps
   docker compose logs -f web
   ```

   `web` debe quedar `healthy`, sin reinicios en loop (`Ctrl+C` para salir de los logs).
6. **Primer administrador**:

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

7. **Verificar**: `curl https://gestion-rh.duckdns.org/salud/` → `{"estado": "ok", ...}`; y `docker ps --format "table {{.Names}}\t{{.Ports}}"` no debe mostrar **ninguna** fila nueva con `0.0.0.0:` (solo `proxy-caddy-1` la tiene).

### Actualizar (redeploy)

```bash
cd /srv/gestion-rh
git pull --ff-only
cd deploy
docker compose up -d --build
```

Si `git pull` da `Permission denied (publickey)`, falta el paso 3 (`git config --local core.sshCommand …`).

### Operación

```bash
cd /srv/gestion-rh/deploy
docker compose ps                  # estado (web debe figurar "healthy")
docker compose logs -f web         # logs de la app
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
