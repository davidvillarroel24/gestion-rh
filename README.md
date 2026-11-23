# Gestión RH — SDMAyRH

Sistema de gestión y seguimiento de proyectos de la Secretaría Departamental de Medio Ambiente y Recursos Hídricos (Gobernación de Cochabamba).

**Stack**: Django 5.2 + GeoDjango · PostgreSQL 17 + PostGIS 3.5 · Docker · dominio **https://gestion-rh.modaldevj.com**

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

## Visor

`/visor/` (es la página a la que se entra después del login): mapa tipo ArcGIS con cinta de herramientas, capas, filtros, tabla de atributos, identificar, medir, ir a coordenada y edición de geometrías (dibujar a mano o por coordenadas). Usa Leaflet, Leaflet-Geoman, proj4 y turf desde la CDN jsDelivr (versiones fijas en `templates/visor/visor.html`). Los mapas base se configuran en `MAPAS_BASE` (`config/settings.py`).

**Clic en un punto, línea o polígono** (sin herramienta activa, o con Identificar): el panel derecho muestra **ese elemento** — tipo, nombre, coordenadas WGS84 y UTM (en líneas y polígonos: longitud o área, perímetro, vértices y centro) y su proyecto —, con botones Ficha del proyecto, Editar geometría y Zoom. Ctrl+clic solo suma a la selección. Los filtros de lista se aplican al elegir; Gestión y Texto, al dejar de escribir.

**Editar / nuevo proyecto sin pasar por /admin**: el botón «Editar proyecto» del panel del proyecto (clic en el mapa o doble clic en la tabla) y «Datos → Nuevo proyecto» ocultan el mapa y muestran, en el mismo lugar, la página `/proyectos/<id>/editar/` (también se abre sola en otra pestaña). Pestañas: datos generales, financiamiento y desembolsos, avance físico, materiales, mediciones, bitácora, documentos, geometrías («Editar en el mapa» vuelve al mapa con esa geometría en edición), detalle de la unidad e historial de cambios. Cada pestaña se guarda por separado y respeta los permisos del rol. «Volver al mapa» conserva filtros y selección y recarga los datos. Código: `proyectos/edicion.py`, `templates/proyectos/editar.html`, `static/visor/js/editor-proyecto.js`. Estas dos páginas permiten mostrarse dentro del visor (`X-Frame-Options: SAMEORIGIN`); el resto del sistema sigue con `DENY`.

## Reportes

`/reportes/` (en el visor: Análisis → Tarjetas y gráficas / Alertas). Con los mismos filtros del visor, guardados en la URL: tarjetas, gráfica y tabla agrupadas por municipio, provincia, región, unidad, estado, programa, tipo, gestión, fuente o entidad, curva S, indicadores antes/después y alertas. Descarga en Excel.

- **Los montos no se duplican**: un proyecto en varios municipios cuenta en cada uno, pero el total se calcula sobre proyectos distintos (la página lo indica). Por municipio se ve también el aporte municipal.
- Umbrales de alertas: `ALERTAS = {"dias_sin_avance": 90, "brecha_financiero_fisico": 25}` en `config/settings.py` (opcional).
- Los estados marcados **«es final»** (Concluido, De baja) no generan alertas de plazo ni de avance.

## Ficha técnica

`/reportes/ficha/` (en el visor: Reportes → Ficha técnica, o el botón «Ficha técnica» del panel de un proyecto). Usa los filtros del visor —incluido **Programa**— o la selección. Se elige **una ficha del conjunto** o **una por proyecto** (máximo 60 por página), se escriben título y objetivo (no se guardan), y se imprime / guarda como PDF desde el navegador o se descarga en Excel con el formato de `1FICHA TECNICA.xlsx`. Los montos van en letras (`reportes/letras.py`).

## Licencias ambientales (área de Fiscalización)

`/licencias/` — sin mapa (D31). Roles propios, separados de proyectos (D32): **Administrador de licencias** (todas las columnas, papelera y configuración) y **Funcionario de licencias** (recepción). El Administrador de proyectos no entra; el superusuario ve todo. Quien solo tiene roles de licencias entra directo a su tabla y no ve el visor.

- **Tabla** (etapa 11.2): pestañas Trámites (IRAP) · Consultas de categoría · Papelera; búsqueda y filtros (municipio, tipo de documento, categoría, tipo de ingreso, técnico, legal, año, fechas); orden por columna; 50 filas por página; **Columnas** elegibles (se recuerdan por usuario, solo entre las que permite su rol); vencidos en rojo y por vencer en amarillo; **Descargar Excel** con lo filtrado.
- **Configuración** (`/licencias/configuracion/`, solo Administrador de licencias): categorías con sus **días** (desde la presentación o el resultado, calendario o hábiles), tipos de documento (anual = IMA; «consulta de categoría» = CNCA), tipos de ingreso, feriados, días de aviso y **columnas que ve el funcionario** (al inicio, las de la app anterior). Lo que ya usan trámites no se borra: se desactiva.
- Valores iniciales (migración `licencias/0002`): tipos de ingreso y los tipos de documento más usados de la planilla. Las categorías las escribe el área.
- Vencimiento: `licencias/plazos.py`. Próximas etapas: formularios y ficha de AOP (11.3), grilla «Pegar desde Excel» (11.4), migración de la planilla y revisor de datos (11.5), alertas (11.6), vínculo con proyectos (11.7).

## Importar y exportar

`/importar/` (en el visor: Datos → Importar / Plantillas Excel / Exportar).

- **Plantillas Excel** por tabla, con listas desplegables. Se escriben códigos de proyecto (`RIE-2026-0001`), nombres de municipio y de catálogo, nunca IDs. Las tablas y sus columnas están definidas en `src/importador/esquemas.py`.
- **Importar** Excel/CSV o mapas (KML, KMZ, GeoJSON, shapefile en .zip): primero se valida (no se guarda nada y se listan los errores por fila), después se confirma. Toda importación aplicada se puede **revertir**.
- **Exportar** a Excel (una hoja por tabla, con los filtros o la selección del visor; se puede corregir y volver a importar), GeoJSON y KML.
- Los archivos subidos quedan en `media/importaciones/` (volumen `media` en Docker) y no son públicos.

## Usuarios, roles y alcance

- Login en `/ingresar/`; después de ingresar cada uno va a su página principal según el rol (`core.alcance.pagina_inicio`: hoy el visor, que ya muestra solo su área; los funcionarios de licencias irán al módulo de licencias en la Fase 11).
- **Usuarios** (`/usuarios/`, solo el Administrador; en el visor: Administración → Usuarios): crear, elegir rol y área (unidades) o municipios, activar/desactivar y cambiar la contraseña. No se borran: se desactivan. «Staff» se marca solo según el rol (todos menos Consulta, para poder editar en la administración).
- **Rol = grupo**: Administrador, Técnico de unidad, Encargado municipal, Funcionario de licencias, Consulta. Sus permisos están en `src/core/roles.py` y se aplican solos después de cada `migrate`.
- **Alcance**: al técnico se le asignan *unidades*; al encargado municipal, *municipios*. `core/alcance.py` filtra todo lo que cada uno ve.
- La pestaña **Administración** del visor y el enlace **Usuarios** solo los ve el Administrador (o un superusuario). «Salir» está en la barra de estado, junto al nombre.
- Catálogos: se crean al usarlos y el sistema avisa si el nombre se parece a uno existente. Valores iniciales tomados del sistema anterior (estados, programas, tipos de proyecto y de elemento, entidades con un gobierno municipal por municipio, indicadores…): `python manage.py cargar_catalogos` — **una vez por base** (PC y VPS); no duplica si se repite. Los valores están en `src/proyectos/datos_iniciales.py`.

## Pruebas

```powershell
cd src
..\.venv\Scripts\python manage.py test
```

(Necesitan permiso para crear una base de prueba con PostGIS; en Docker funcionan directo.)

## Despliegue en el VPS compartido (Contabo)

El VPS lo comparten varios proyectos. **Solo el proxy compartido** (Caddy en `/srv/proxy`) usa los puertos 80/443: este stack no publica puertos, se conecta a la red `proxy` y declara su dominio con las etiquetas `caddy` del servicio `web`. La base de datos queda en la red interna `interna`, sin acceso desde afuera ni desde otros proyectos. Cada contenedor tiene límite de memoria y CPU.

Pasos probados en este VPS (mismo flujo que funcionó con los otros proyectos), como `root` por PuTTY. **Pegar cada comando en una sola línea**: PuTTY puede romper los `\` de continuación.

1. **DNS (Cloudflare, dominio `modaldevj.com`)**: registro `A` `gestion-rh` → IP del VPS, con el proxy en **«DNS only»** (nube gris) para que el proxy compartido saque el certificado de Let's Encrypt directo. Comprobar: `nslookup gestion-rh.modaldevj.com` debe devolver la IP del VPS. (Antes se usó `gestion-rh.duckdns.org`; la red de la Gobernación bloquea todo `*.duckdns.org`.)
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

   `DOMINIO=gestion-rh.modaldevj.com`, `DJANGO_DEBUG=0`. **No** copiar las líneas de Windows (`DB_HOST`, `GDAL_LIBRARY_PATH`…) del `.env` de la PC.
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

7. **Verificar**: `curl https://gestion-rh.modaldevj.com/salud/` → `{"estado": "ok", ...}`; y `docker ps --format "table {{.Names}}\t{{.Ports}}"` no debe mostrar **ninguna** fila nueva con `0.0.0.0:` (solo `proxy-caddy-1` la tiene).

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
