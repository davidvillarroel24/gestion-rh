"""
Importación espacial (README de diseño §8.1): KML, KMZ, GeoJSON o shapefile en .zip.

Destinos:
- "geometrias": las figuras pasan a ser geometrías de un proyecto, con un tipo
  de elemento por forma (punto / línea / polígono).
- "limites": actualiza la forma de municipios existentes (solo administración).

Mismo esquema que la importación tabular: validar (todo se ensaya y se deshace)
y después confirmar; los cambios quedan registrados para poder revertir.
"""

import os
import shutil
import tempfile
import zipfile

from django.contrib.gis.gdal import DataSource, GDALException, SpatialReference
from django.contrib.gis.geos import MultiPolygon
from django.db import transaction
from django.utils import timezone

from proyectos import consultas
from proyectos.models import Geometria, TipoElemento
from territorio.servicios import recalcular_agregados

from .esquemas import Contexto, ErrorFila, _guardar
from .models import Cambio, Importacion
from .tabular import _guardar_cambios

# Proyección de los shapefiles originales del departamento (carpeta planos/).
LAMBERT_COCHABAMBA = ("+proj=lcc +lat_1=-15 +lat_2=-19 +lat_0=-19 +lon_0=-66 +x_0=200000 +y_0=0 "
                      "+datum=WGS84 +units=m +no_defs")
SISTEMAS = [("4326", "WGS84 (latitud/longitud)"), ("32719", "UTM 19S"), ("32720", "UTM 20S"),
            ("lambert", "Lambert del departamento (planos originales)")]
EXTENSIONES = (".kml", ".kmz", ".geojson", ".json", ".zip")
FORMAS = {"Point": "Point", "LineString": "LineString", "Polygon": "Polygon"}
NOMBRE_FORMA = {"Point": "puntos", "LineString": "líneas", "Polygon": "polígonos"}


class ErrorArchivo(Exception):
    pass


def _srs(sistema):
    return SpatialReference(LAMBERT_COCHABAMBA if sistema == "lambert" else int(sistema or 4326))


def _preparar(archivo, nombre, carpeta):
    """Copia/extrae el archivo a una carpeta temporal y devuelve la ruta que lee GDAL."""
    nombre = nombre.lower()
    if not nombre.endswith(EXTENSIONES):
        raise ErrorArchivo("Formato no soportado: use .kml, .kmz, .geojson o un shapefile en .zip.")
    destino = os.path.join(carpeta, "entrada" + os.path.splitext(nombre)[1])
    with open(destino, "wb") as salida:
        shutil.copyfileobj(archivo, salida)
    if not nombre.endswith((".zip", ".kmz")):
        return destino
    try:
        with zipfile.ZipFile(destino) as z:
            for miembro in z.namelist():  # nunca extraer fuera de la carpeta temporal
                if miembro.startswith(("/", "\\")) or ".." in miembro.replace("\\", "/").split("/"):
                    raise ErrorArchivo("El .zip contiene rutas no permitidas.")
            z.extractall(os.path.join(carpeta, "zip"))
    except zipfile.BadZipFile:
        raise ErrorArchivo("El archivo comprimido está dañado.")
    for raiz, _, archivos in os.walk(os.path.join(carpeta, "zip")):
        for buscado in (".kml", ".shp", ".geojson"):
            for a in sorted(archivos):
                if a.lower().endswith(buscado):
                    return os.path.join(raiz, a)
    raise ErrorArchivo("No se encontró un .kml, .shp o .geojson dentro del comprimido.")


def _partes(geom):
    """Las multi-geometrías se separan: cada parte es una geometría del sistema."""
    if geom.geom_type in ("MultiPoint", "MultiLineString", "MultiPolygon", "GeometryCollection"):
        for parte in geom:
            yield from _partes(parte)
    else:
        yield geom


def leer(archivo, nombre, sistema=None):
    """Lista de elementos {geom (GEOS, WGS84), atributos} + datos de la capa."""
    carpeta = tempfile.mkdtemp(prefix="importacion_")
    try:
        ruta = _preparar(archivo, nombre, carpeta)
        try:
            fuente = DataSource(ruta)
        except GDALException:
            raise ErrorArchivo("No se pudo leer el archivo espacial.")
        elementos, atributos, sin_srs = [], [], False
        destino = SpatialReference(4326)
        for capa in fuente:
            atributos += [a for a in capa.fields if a not in atributos]
            for feature in capa:
                ogr = feature.geom
                if ogr is None:
                    continue
                ogr.coord_dim = 2  # KML trae altura: se descarta
                if capa.srs is None:
                    sin_srs = True
                    ogr.srs = _srs(sistema)
                ogr.transform(destino)
                propiedades = {}
                for campo in capa.fields:
                    valor = feature.get(campo)
                    propiedades[campo] = "" if valor is None else str(valor)
                for parte in _partes(ogr.geos):
                    parte.srid = 4326
                    elementos.append({"geom": parte, "atributos": propiedades})
        return {"elementos": elementos, "atributos": atributos, "sin_srs": sin_srs}
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def leer_importacion(importacion):
    with importacion.archivo.open("rb") as archivo:
        return leer(archivo, importacion.nombre_archivo, importacion.opciones.get("sistema"))


def resumen_lectura(lectura):
    formas = {}
    for e in lectura["elementos"]:
        formas[e["geom"].geom_type] = formas.get(e["geom"].geom_type, 0) + 1
    return {"elementos": len(lectura["elementos"]), "formas": formas, "atributos": lectura["atributos"],
            "sin_srs": lectura["sin_srs"]}


# ---------------------------------------------------------------- destinos


def _a_geometrias(lectura, opciones, ctx):
    resultado = {"creados": 0, "sin_cambios": 0, "relaciones": 0, "errores": []}
    elegido = str(opciones.get("proyecto") or "")
    proyecto = consultas.visibles(ctx.usuario).filter(pk=int(elegido)).first() if elegido.isdigit() else None
    if proyecto is None:
        resultado["errores"].append({"fila": None, "mensajes": ["Elija un proyecto de su alcance."]})
        return resultado
    tipos = {}
    for forma in FORMAS:
        elegido = str(opciones.get(f"tipo_{forma}") or "")
        tipos[forma] = (TipoElemento.objects.filter(pk=int(elegido), unidad=proyecto.unidad, activo=True).first()
                        if elegido.isdigit() else None)
    atributo = opciones.get("atributo_nombre") or ""
    for i, elemento in enumerate(lectura["elementos"], start=1):
        geom, nombre = elemento["geom"], elemento["atributos"].get(atributo, "")[:150]
        etiqueta = f"Elemento {i}" + (f" ({nombre})" if nombre else "")
        tipo = tipos.get(geom.geom_type)
        if tipo is None:
            resultado["errores"].append({"fila": i, "mensajes": [f"{etiqueta}: elija el tipo de elemento para los {NOMBRE_FORMA.get(geom.geom_type, geom.geom_type)}."]})
            continue
        if Geometria.objects.filter(proyecto=proyecto, tipo_elemento=tipo, geom__equals=geom).exists():
            resultado["sin_cambios"] += 1
            continue
        try:
            with transaction.atomic():
                ctx.permiso(Geometria, "add")
                _guardar(Geometria(proyecto=proyecto, tipo_elemento=tipo, nombre=nombre, geom=geom), ctx, True)
            resultado["creados"] += 1
        except ErrorFila as e:
            resultado["errores"].append({"fila": i, "mensajes": [f"{etiqueta}: {m}" for m in e.mensajes]})
    if not resultado["errores"] and not proyecto.municipios.exists():
        for geometria in proyecto.geometrias.all():
            for municipio in geometria.municipios_que_toca():
                if not proyecto.municipios.filter(pk=municipio.pk).exists():
                    proyecto.municipios.add(municipio)
                    ctx.registrar(proyecto, Cambio.RELACION, extra={"municipio": municipio.pk})
                    resultado["relaciones"] += 1
    return resultado


def _a_limites(lectura, opciones, ctx):
    resultado = {"actualizados": 0, "sin_cambios": 0, "errores": []}
    if not ctx.usuario.has_perm("territorio.change_municipio"):
        resultado["errores"].append({"fila": None, "mensajes": ["Su rol no permite actualizar límites."]})
        return resultado
    atributo = opciones.get("atributo_municipio") or ""
    # Las partes de un mismo municipio (islas) se juntan de nuevo en un MultiPolygon.
    por_municipio, errores = {}, []
    for i, elemento in enumerate(lectura["elementos"], start=1):
        valor = elemento["atributos"].get(atributo, "").strip()
        municipio = ctx.municipio(valor) if valor else None
        if municipio is None:
            errores.append({"fila": i, "mensajes": [f"Elemento {i}: no hay un municipio «{valor}» (atributo «{atributo}»)."]})
        elif elemento["geom"].geom_type != "Polygon":
            errores.append({"fila": i, "mensajes": [f"Elemento {i}: un límite debe ser un polígono."]})
        else:
            por_municipio.setdefault(municipio, []).append(elemento["geom"])
    resultado["errores"] = errores
    for municipio, poligonos in por_municipio.items():
        nueva = MultiPolygon(*poligonos, srid=4326)
        if municipio.geom.equals_exact(nueva, tolerance=1e-9):
            resultado["sin_cambios"] += 1
            continue
        try:
            with transaction.atomic():
                municipio.geom = nueva
                _guardar(municipio, ctx, False)
            resultado["actualizados"] += 1
        except ErrorFila as e:
            resultado["errores"].append({"fila": None, "mensajes": [f"{municipio}: {m}" for m in e.mensajes]})
    if resultado["actualizados"] and not resultado["errores"]:
        recalcular_agregados()
    return resultado


DESTINOS = {"geometrias": ("Geometrías de un proyecto", _a_geometrias), "limites": ("Límites municipales", _a_limites)}


def ejecutar(importacion, aplicar=False):
    ctx = Contexto(importacion.usuario)
    try:
        lectura = leer_importacion(importacion)
    except ErrorArchivo as e:
        importacion.resumen = {"errores": [{"fila": None, "mensajes": [str(e)]}]}
        importacion.estado = Importacion.CON_ERRORES
        importacion.save()
        return importacion

    with transaction.atomic():
        resultado = DESTINOS[importacion.destino][1](lectura, importacion.opciones, ctx)
        if resultado["errores"] or not aplicar:
            transaction.set_rollback(True)
        else:
            _guardar_cambios(importacion, ctx)

    importacion.resumen = {**resumen_lectura(lectura), **resultado}
    if resultado["errores"]:
        importacion.estado = Importacion.CON_ERRORES
    elif aplicar:
        importacion.estado = Importacion.APLICADA
        importacion.aplicada_en = timezone.now()
    else:
        importacion.estado = Importacion.VALIDADA
    importacion.save()
    return importacion


def vista_previa(importacion, maximo=5000):
    """GeoJSON de lo que trae el archivo (para el mapa de la página de la importación)."""
    import json

    lectura = leer_importacion(importacion)
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": json.loads(e["geom"].geojson), "properties": e["atributos"]}
        for e in lectura["elementos"][:maximo]
    ]}
