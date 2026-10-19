from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.core.cache import cache
from django.db import transaction

from .models import Municipio, Provincia, Region

# Huecos menores a esto que quedan al unir municipios son espacios entre
# límites (hay ~900, el mayor ≈3 km²), no territorio real. El municipio
# más chico (Tacachi) tiene 17 km², así que no se pierde ningún enclave.
HUECO_MAXIMO_KM2 = 5

# SRID métrico solo para medir áreas de huecos (la diferencia entre zonas 19S y 20S
# no importa para este umbral).
SRID_METRICO = 32720

CLAVE_CACHE_DEPARTAMENTO = "territorio:departamento"
CLAVE_CACHE_VERSION = "territorio:version"


def version_cache():
    """Cambia cada vez que se recalculan los límites: invalida el GeoJSON cacheado."""
    return cache.get_or_set(CLAVE_CACHE_VERSION, 1, None)


def _sin_huecos_chicos(geom):
    """Une y devuelve un MultiPolygon sin los anillos interiores pequeños."""
    poligonos = []
    for poligono in (geom if geom.geom_type == "MultiPolygon" else [geom]):
        conservar = []
        for i in range(1, len(poligono)):
            anillo = poligono[i]
            hueco = Polygon(anillo, srid=geom.srid)
            if hueco.transform(SRID_METRICO, clone=True).area / 1e6 >= HUECO_MAXIMO_KM2:
                conservar.append(anillo)
        poligonos.append(Polygon(poligono[0], *conservar, srid=geom.srid))
    return MultiPolygon(*poligonos, srid=geom.srid)


def unir(geometrias):
    poligonos = [p for g in geometrias for p in g]
    if not poligonos:
        return None
    return _sin_huecos_chicos(MultiPolygon(*poligonos, srid=4326).unary_union)


@transaction.atomic
def recalcular_agregados():
    """Recalcula la geometría de provincias y regiones a partir de sus municipios."""
    for modelo in (Provincia, Region):
        for agregado in modelo.objects.all():
            agregado.geom = unir(m.geom for m in agregado.municipios.all())
            agregado.save(update_fields=["geom"])
    cache.delete(CLAVE_CACHE_DEPARTAMENTO)
    cache.set(CLAVE_CACHE_VERSION, version_cache() + 1, None)


def departamento():
    """Geometría del departamento (unión de todas las regiones), cacheada."""
    wkb = cache.get(CLAVE_CACHE_DEPARTAMENTO)
    if wkb is not None:
        return GEOSGeometry(memoryview(wkb), srid=4326)
    geom = unir(r.geom for r in Region.objects.exclude(geom=None))
    if geom is not None:
        cache.set(CLAVE_CACHE_DEPARTAMENTO, bytes(geom.wkb), None)
    return geom
