import json

from django.core.cache import cache
from django.db.models import FloatField, Func, Sum
from django.http import Http404, HttpResponse

from . import servicios
from .models import Municipio, Provincia, Region


class AreaKm2(Func):
    """Área real en km² (PostGIS sobre geography, sin depender de la zona UTM)."""

    template = "ST_Area(%(expressions)s::geography) / 1000000.0"
    output_field = FloatField()


def tolerancia_para_zoom(z):
    """Grados de simplificación según el zoom del mapa (menos detalle al alejarse)."""
    if z <= 7:
        return 0.005
    if z <= 9:
        return 0.002
    if z <= 11:
        return 0.0005
    if z <= 13:
        return 0.0001
    return 0


def _feature(geom, propiedades, tolerancia):
    if tolerancia:
        geom = geom.simplify(tolerancia, preserve_topology=True)
    return {"type": "Feature", "geometry": json.loads(geom.geojson), "properties": propiedades}


def _municipios(tol):
    qs = Municipio.objects.select_related("provincia", "region").annotate(area_km2=AreaKm2("geom"))
    return [
        _feature(m.geom, {
            "id": m.id, "nombre": m.nombre, "codigo_ine": m.codigo_ine, "es_tioc": m.es_tioc,
            "provincia": m.provincia.nombre, "region": m.region.nombre, "area_km2": round(m.area_km2, 1),
        }, tol)
        for m in qs
    ]


def _agregados(modelo, tol):
    qs = modelo.objects.exclude(geom=None).annotate(area_km2=AreaKm2("geom"))
    return [
        _feature(a.geom, {"id": a.id, "nombre": a.nombre, "area_km2": round(a.area_km2, 1)}, tol)
        for a in qs
    ]


def _departamento(tol):
    geom = servicios.departamento()
    if geom is None:
        return []
    area = Region.objects.exclude(geom=None).aggregate(total=Sum(AreaKm2("geom")))["total"]
    return [_feature(geom, {"nombre": "Cochabamba", "area_km2": round(area or 0, 1)}, tol)]


CAPAS = {
    "municipios": _municipios,
    "provincias": lambda tol: _agregados(Provincia, tol),
    "regiones": lambda tol: _agregados(Region, tol),
    "departamento": _departamento,
}


def capa_geojson(request, capa):
    """GeoJSON de una capa de límites: /territorio/<capa>.geojson?z=<zoom>"""
    if capa not in CAPAS:
        raise Http404("Capa desconocida")
    try:
        z = int(request.GET.get("z", 8))
    except ValueError:
        z = 8
    tol = tolerancia_para_zoom(z)

    clave = f"territorio:geojson:{servicios.version_cache()}:{capa}:{tol}"
    contenido = cache.get(clave)
    if contenido is None:
        contenido = json.dumps({"type": "FeatureCollection", "features": CAPAS[capa](tol)}, ensure_ascii=False)
        cache.set(clave, contenido, None)
    return HttpResponse(contenido, content_type="application/geo+json")
