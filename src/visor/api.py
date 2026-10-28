"""
API JSON del visor. Todo filtrado por el alcance del usuario (core.alcance).

GET    /visor/api/config/                 mapas base, unidades, catálogos, permisos
GET    /visor/api/geometrias/?unidad=&estado=&municipio=&gestion=&q=&bbox=   GeoJSON
POST   /visor/api/geometrias/             crea una geometría dibujada en el mapa
PATCH  /visor/api/geometrias/<id>/        cambia forma, tipo o nombre
DELETE /visor/api/geometrias/<id>/
GET    /visor/api/proyectos/?…            filas de la tabla de atributos
GET    /visor/api/proyectos/<id>/         ficha para "Identificar"
"""

import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import GEOSException, GEOSGeometry, Polygon
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from core import alcance
from proyectos import consultas
from proyectos.models import EstadoProyecto, Geometria, TipoElemento
from territorio.models import Provincia, Region
from territorio.servicios import departamento


def _error(mensaje, status=400, **extra):
    return JsonResponse({"error": mensaje, **extra}, status=status)


def _cuerpo(request):
    try:
        return json.loads(request.body or "{}")
    except ValueError:
        return None


def _num(valor):
    return float(valor) if valor is not None else None


def _errores_validacion(e):
    return {campo: [str(m) for m in mensajes] for campo, mensajes in e.message_dict.items()}


@login_required
def config(request):
    u = request.user
    limite = departamento()
    unidades = alcance.unidades_visibles(u).filter(activo=True)
    return JsonResponse({
        "usuario": {"nombre": u.get_full_name() or u.username, "roles": sorted(alcance.nombres_de_roles(u))},
        "mapas_base": settings.MAPAS_BASE,
        "extension": limite.extent if limite else None,  # [oeste, sur, este, norte]
        "unidades": [{"id": x.id, "nombre": x.nombre} for x in unidades],
        "estados": [{"id": x.id, "nombre": x.nombre} for x in EstadoProyecto.objects.filter(activo=True)],
        # Con su provincia y región: los filtros del visor van en cascada (Región → Provincia → Municipio).
        "municipios": [{"id": m.id, "nombre": m.nombre, "provincia": m.provincia_id, "region": m.region_id}
                       for m in alcance.municipios_visibles(u).order_by("nombre")],
        "provincias": [{"id": p.id, "nombre": p.nombre} for p in Provincia.objects.order_by("nombre")],
        "regiones": [{"id": r.id, "nombre": r.nombre} for r in Region.objects.order_by("nombre")],
        "tipos_elemento": [
            {"id": t.id, "nombre": t.nombre, "unidad": t.unidad_id, "tipo_geometria": t.tipo_geometria}
            for t in TipoElemento.objects.filter(activo=True, unidad__in=unidades)
        ],
        "permisos": {
            "crear_geometria": u.has_perm("proyectos.add_geometria"),
            "editar_geometria": u.has_perm("proyectos.change_geometria"),
            "borrar_geometria": u.has_perm("proyectos.delete_geometria"),
            "crear_proyecto": u.has_perm("proyectos.add_proyecto"),
            "administracion": u.is_staff,
        },
    })


def _feature(g):
    p = g.proyecto
    return {
        "type": "Feature",
        "id": g.id,
        "geometry": json.loads(g.geom.geojson),
        "properties": {
            "id": g.id, "nombre": g.nombre, "tipo_elemento": g.tipo_elemento.nombre, "tipo_elemento_id": g.tipo_elemento_id,
            "proyecto_id": p.id, "codigo": p.codigo, "proyecto": p.nombre,
            "unidad_id": p.unidad_id, "unidad": p.unidad.nombre,
            "estado": p.estado.nombre if p.estado_id else None,
        },
    }


def _geometrias_visibles(usuario):
    return Geometria.objects.filter(proyecto__in=consultas.visibles(usuario)).select_related(
        "proyecto__unidad", "proyecto__estado", "tipo_elemento")


@login_required
@require_http_methods(["GET", "POST"])
def geometrias(request):
    if request.method == "POST":
        return _crear_geometria(request)
    if not request.user.has_perm("proyectos.view_geometria"):
        return _error("Sin permiso", 403)
    proyectos = consultas.filtrar(consultas.visibles(request.user), request.GET)
    qs = _geometrias_visibles(request.user).filter(proyecto__in=proyectos)
    if request.GET.get("proyecto"):
        qs = qs.filter(proyecto_id=request.GET["proyecto"])
    if request.GET.get("bbox"):
        try:
            qs = qs.filter(geom__intersects=Polygon.from_bbox([float(v) for v in request.GET["bbox"].split(",")]))
        except (ValueError, TypeError):
            return _error("bbox inválido: oeste,sur,este,norte")
    return JsonResponse({"type": "FeatureCollection", "features": [_feature(g) for g in qs]})


def _leer_geom(valor):
    try:
        geom = GEOSGeometry(json.dumps(valor), srid=4326)
    except (GEOSException, ValueError, TypeError):
        raise ValidationError({"geom": "Geometría inválida."})
    if geom.geom_type == "MultiPoint" and len(geom) == 1:
        geom = geom[0]
    return geom


def _guardar(geometria):
    geometria.full_clean()
    geometria.save()
    proyecto = geometria.proyecto
    if not proyecto.municipios.exists():
        proyecto.municipios.add(*geometria.municipios_que_toca())


def _crear_geometria(request):
    if not request.user.has_perm("proyectos.add_geometria"):
        return _error("Su rol no permite dibujar geometrías.", 403)
    datos = _cuerpo(request)
    if datos is None:
        return _error("JSON inválido.")
    proyecto = consultas.visibles(request.user).filter(pk=datos.get("proyecto")).first()
    if proyecto is None:
        return _error("Proyecto inexistente o fuera de su alcance.", 404)
    tipo = TipoElemento.objects.filter(pk=datos.get("tipo_elemento"), activo=True).first()
    if tipo is None:
        return _error("Tipo de elemento inexistente.")
    try:
        g = Geometria(proyecto=proyecto, tipo_elemento=tipo, nombre=str(datos.get("nombre", ""))[:150],
                      geom=_leer_geom(datos.get("geometry")))
        _guardar(g)
    except ValidationError as e:
        return _error("No se pudo guardar.", 400, detalle=_errores_validacion(e))
    return JsonResponse(_feature(g), status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def geometria(request, pk):
    g = _geometrias_visibles(request.user).filter(pk=pk).first()
    if g is None:
        raise Http404
    if request.method == "DELETE":
        if not request.user.has_perm("proyectos.delete_geometria"):
            return _error("Su rol no permite borrar geometrías.", 403)
        g.delete()
        return JsonResponse({"ok": True})

    if not request.user.has_perm("proyectos.change_geometria"):
        return _error("Su rol no permite editar geometrías.", 403)
    datos = _cuerpo(request)
    if datos is None:
        return _error("JSON inválido.")
    try:
        if "geometry" in datos:
            g.geom = _leer_geom(datos["geometry"])
        if "tipo_elemento" in datos:
            g.tipo_elemento = TipoElemento.objects.get(pk=datos["tipo_elemento"], activo=True)
        if "nombre" in datos:
            g.nombre = str(datos["nombre"])[:150]
        _guardar(g)
    except TipoElemento.DoesNotExist:
        return _error("Tipo de elemento inexistente.")
    except ValidationError as e:
        return _error("No se pudo guardar.", 400, detalle=_errores_validacion(e))
    return JsonResponse(_feature(g))


@login_required
def proyectos(request):
    """Filas de la tabla de atributos."""
    if not request.user.has_perm("proyectos.view_proyecto"):
        return _error("Sin permiso", 403)
    qs = consultas.con_totales(consultas.filtrar(consultas.visibles(request.user), request.GET))
    qs = qs.select_related("unidad", "estado", "programa", "tipo").prefetch_related("municipios")
    filas = []
    for p in qs.order_by("codigo"):
        costo, pagado = p.total_comprometido, p.total_desembolsado
        filas.append({
            "id": p.id, "codigo": p.codigo, "nombre": p.nombre, "unidad_id": p.unidad_id, "unidad": p.unidad.nombre,
            "programa": p.programa.nombre if p.programa_id else "", "tipo": p.tipo.nombre if p.tipo_id else "",
            "estado": p.estado.nombre if p.estado_id else "", "gestion": p.gestion,
            "municipios": ", ".join(m.nombre for m in p.municipios.all()),
            "costo_total": _num(costo), "desembolsado": _num(pagado),
            "avance_financiero": round(float(pagado) * 100 / float(costo), 1) if costo else None,
            "avance_fisico": _num(p.ultimo_avance_fisico),
        })
    return JsonResponse({"filas": filas})


def _url_admin(nombre, *args):
    try:
        return reverse(nombre, args=args)
    except NoReverseMatch:
        return None


@login_required
def proyecto(request, pk):
    """Ficha que muestra "Identificar"."""
    p = consultas.con_totales(consultas.visibles(request.user)).filter(pk=pk).first()
    if p is None:
        raise Http404
    u = request.user
    ultimo = p.eventos.select_related("tipo").first()
    datos = {
        "id": p.id, "codigo": p.codigo, "nombre": p.nombre, "unidad": p.unidad.nombre,
        "programa": str(p.programa or ""), "tipo": str(p.tipo or ""), "estado": str(p.estado or ""),
        "gestion": p.gestion, "sisin": p.sisin, "comunidad": p.comunidad,
        "municipios": [m.nombre for m in p.municipios.all()],
        "fecha_orden_proceder": p.fecha_orden_proceder, "fecha_conclusion": p.fecha_conclusion, "plazo_dias": p.plazo_dias,
        "costo_total": _num(p.total_comprometido), "desembolsado": _num(p.total_desembolsado),
        "avance_fisico": _num(p.ultimo_avance_fisico),
        "avance_financiero": _num(p.avance_financiero),
        "financiamiento": [{"entidad": f.entidad.nombre, "comprometido": _num(f.monto_comprometido), "desembolsado": _num(f.desembolsado)}
                           for f in p.financiamientos.select_related("entidad")],
        "ultimo_evento": {"fecha": ultimo.fecha, "tipo": ultimo.tipo.nombre, "descripcion": ultimo.descripcion} if ultimo else None,
        "mediciones": [{"indicador": str(m.indicador), "desagregacion": str(m.desagregacion or ""), "momento": m.get_momento_display(),
                        "fecha": m.fecha, "valor": _num(m.valor)}
                       for m in p.mediciones.select_related("indicador", "desagregacion")],
        "documentos": [{"nombre": str(d), "tipo": str(d.tipo or ""), "url": reverse("proyectos:descargar_documento", args=[d.pk])}
                       for d in p.documentos.select_related("tipo")] if u.has_perm("proyectos.view_documento") else [],
        "url_admin": _url_admin("admin:proyectos_proyecto_change", p.pk) if u.is_staff else None,
    }
    return JsonResponse(datos)
