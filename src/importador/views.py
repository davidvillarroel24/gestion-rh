"""
Páginas de importación (Datos → Importar en el visor) y descargas de
plantillas y exportaciones (Datos → Exportar).
"""

import io
import json
from datetime import date
from xml.sax.saxutils import escape

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core import alcance
from proyectos import consultas
from proyectos.models import Geometria, TipoElemento

from . import espacial, tabular
from .esquemas import TABLAS, TABLAS_DE_PROYECTOS
from .models import Importacion
from .reversion import puede_revertir, revertir

TAMANO_MAXIMO = 20 * 1024 * 1024  # 20 MB
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _es_admin(usuario):
    return usuario.is_superuser or usuario.groups.filter(name="Administrador").exists()


def _importaciones_visibles(usuario):
    qs = Importacion.objects.select_related("usuario")
    return qs if _es_admin(usuario) else qs.filter(usuario=usuario)


def _tablas_permitidas(usuario):
    return [t for t in TABLAS.values()
            if usuario.has_perm(f"{t.modelo._meta.app_label}.add_{t.modelo._meta.model_name}")
            or usuario.has_perm(f"{t.modelo._meta.app_label}.change_{t.modelo._meta.model_name}")]


def _archivo_valido(request, archivo):
    if archivo is None:
        messages.error(request, "Elija un archivo.")
        return False
    if archivo.size > TAMANO_MAXIMO:
        messages.error(request, "El archivo supera los 20 MB.")
        return False
    return True


@login_required
def inicio(request):
    return render(request, "importador/inicio.html", {
        "tablas": _tablas_permitidas(request.user),
        "importaciones": _importaciones_visibles(request.user)[:50],
        "sistemas": espacial.SISTEMAS,
        "destinos": [(k, nombre) for k, (nombre, _) in espacial.DESTINOS.items()
                     if k != "limites" or request.user.has_perm("territorio.change_municipio")],
    })


@login_required
@require_POST
def subir_tabular(request):
    tabla = TABLAS.get(request.POST.get("tabla"))
    archivo = request.FILES.get("archivo")
    if tabla is None or tabla not in _tablas_permitidas(request.user):
        messages.error(request, "Elija una tabla que su rol pueda cargar.")
        return redirect("importador:inicio")
    if not _archivo_valido(request, archivo):
        return redirect("importador:inicio")
    importacion = Importacion.objects.create(
        tipo=Importacion.TABULAR, destino=tabla.clave, archivo=archivo, nombre_archivo=archivo.name,
        usuario=request.user, opciones={"crear_catalogos": request.POST.get("crear_catalogos") == "1"})
    tabular.ejecutar(importacion, aplicar=False)
    return redirect("importador:detalle", importacion.pk)


@login_required
@require_POST
def subir_espacial(request):
    destino = request.POST.get("destino")
    archivo = request.FILES.get("archivo")
    if destino not in espacial.DESTINOS or (destino == "limites" and not request.user.has_perm("territorio.change_municipio")):
        messages.error(request, "Destino no válido.")
        return redirect("importador:inicio")
    if not _archivo_valido(request, archivo):
        return redirect("importador:inicio")
    importacion = Importacion.objects.create(
        tipo=Importacion.ESPACIAL, destino=destino, archivo=archivo, nombre_archivo=archivo.name,
        usuario=request.user, opciones={"sistema": request.POST.get("sistema") or "4326"})
    try:
        importacion.resumen = espacial.resumen_lectura(espacial.leer_importacion(importacion))
    except espacial.ErrorArchivo as e:
        importacion.resumen = {"errores": [{"fila": None, "mensajes": [str(e)]}]}
        importacion.estado = Importacion.CON_ERRORES
    importacion.save()
    return redirect("importador:detalle", importacion.pk)


def _importacion(request, pk):
    return get_object_or_404(_importaciones_visibles(request.user), pk=pk)


@login_required
def detalle(request, pk):
    importacion = _importacion(request, pk)
    contexto = {"importacion": importacion, "puede_revertir": puede_revertir(importacion, request.user)}
    if importacion.tipo == Importacion.TABULAR:
        contexto["tabla"] = TABLAS[importacion.destino]
    else:
        contexto["destino_nombre"] = espacial.DESTINOS[importacion.destino][0]
        contexto["sistemas"] = espacial.SISTEMAS
        contexto["formas"] = [(f, espacial.NOMBRE_FORMA[f], importacion.opciones.get(f"tipo_{f}", ""))
                              for f in espacial.FORMAS if f in importacion.resumen.get("formas", {})]
        contexto["formas_texto"] = " · ".join(f"{n} {espacial.NOMBRE_FORMA.get(f, f)}"
                                              for f, n in importacion.resumen.get("formas", {}).items())
        if importacion.destino == "geometrias":
            proyectos = consultas.visibles(request.user).select_related("unidad").order_by("codigo")
            contexto["proyectos"] = proyectos
            # Se pasan con json_script (seguro aunque un nombre traiga "</script>").
            contexto["tipos_elemento"] = [
                {"id": t.id, "nombre": t.nombre, "unidad": t.unidad_id, "forma": t.tipo_geometria}
                for t in TipoElemento.objects.filter(activo=True, unidad__in=alcance.unidades_visibles(request.user))]
            contexto["unidad_de_proyecto"] = {p.id: p.unidad_id for p in proyectos}
    return render(request, "importador/detalle.html", contexto)


@login_required
@require_POST
def opciones_espaciales(request, pk):
    importacion = _importacion(request, pk)
    if importacion.tipo != Importacion.ESPACIAL or importacion.estado in (Importacion.APLICADA, Importacion.REVERTIDA):
        raise Http404
    claves = ["sistema", "proyecto", "atributo_nombre", "atributo_municipio"] + [f"tipo_{f}" for f in espacial.FORMAS]
    importacion.opciones = {k: request.POST.get(k, "") for k in claves}
    importacion.save()
    espacial.ejecutar(importacion, aplicar=False)
    return redirect("importador:detalle", importacion.pk)


@login_required
@require_POST
def confirmar(request, pk):
    importacion = _importacion(request, pk)
    if importacion.estado != Importacion.VALIDADA or importacion.usuario_id != request.user.pk:
        messages.error(request, "Solo quien la cargó puede confirmar una importación validada.")
        return redirect("importador:detalle", pk)
    modulo = tabular if importacion.tipo == Importacion.TABULAR else espacial
    modulo.ejecutar(importacion, aplicar=True)
    if importacion.estado == Importacion.APLICADA:
        messages.success(request, "Importación aplicada.")
    else:
        messages.error(request, "Los datos cambiaron desde la validación y ahora hay errores; revise y vuelva a intentar.")
    return redirect("importador:detalle", pk)


@login_required
@require_POST
def deshacer(request, pk):
    importacion = _importacion(request, pk)
    if not puede_revertir(importacion, request.user):
        raise Http404
    problemas = revertir(importacion)
    if problemas:
        messages.error(request, "No se pudo revertir: " + " ".join(problemas))
    else:
        messages.success(request, "Importación revertida.")
    return redirect("importador:detalle", pk)


@login_required
def errores_xlsx(request, pk):
    importacion = _importacion(request, pk)
    if importacion.tipo != Importacion.TABULAR:
        raise Http404
    return _respuesta_xlsx(tabular.libro_de_errores(importacion), f"errores-{importacion.pk}.xlsx")


@login_required
def vista_previa(request, pk):
    importacion = _importacion(request, pk)
    if importacion.tipo != Importacion.ESPACIAL:
        raise Http404
    try:
        return JsonResponse(espacial.vista_previa(importacion))
    except espacial.ErrorArchivo as e:
        return JsonResponse({"error": str(e)}, status=400)


# ---------------------------------------------------------------- plantillas y exportaciones


def _respuesta_xlsx(libro, nombre):
    salida = io.BytesIO()
    libro.save(salida)
    respuesta = HttpResponse(salida.getvalue(), content_type=XLSX)
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return respuesta


@login_required
def plantilla(request, clave):
    tabla = TABLAS.get(clave)
    if tabla is None or tabla not in _tablas_permitidas(request.user):
        raise Http404
    return _respuesta_xlsx(tabular.plantilla(tabla, request.user), f"plantilla-{clave}.xlsx")


def _proyectos_exportables(request):
    """Proyectos visibles con los mismos filtros del visor (y la selección, si viene ?ids=)."""
    qs = consultas.filtrar(consultas.visibles(request.user), request.GET)
    if request.GET.get("ids"):
        ids = [int(x) for x in request.GET["ids"].split(",") if x.strip().isdigit()]
        qs = qs.filter(pk__in=ids)
    return qs


@login_required
def exportar_excel(request):
    claves = [c for c in request.GET.get("tablas", "").split(",") if c]
    tablas = [TABLAS[c] for c in claves if c in TABLAS] or TABLAS_DE_PROYECTOS
    tablas = [t for t in tablas if request.user.has_perm(f"{t.modelo._meta.app_label}.view_{t.modelo._meta.model_name}")]
    if not tablas:
        raise Http404
    nombre = f"gestion-rh-{tablas[0].clave if len(tablas) == 1 else 'proyectos'}-{date.today():%Y-%m-%d}.xlsx"
    return _respuesta_xlsx(tabular.exportar(tablas, _proyectos_exportables(request), request.user), nombre)


def _geometrias_exportables(request):
    if not request.user.has_perm("proyectos.view_geometria"):
        raise Http404
    return Geometria.objects.filter(proyecto__in=_proyectos_exportables(request)).select_related(
        "proyecto__unidad", "proyecto__estado", "tipo_elemento").order_by("proyecto__codigo", "id")


def _propiedades(g):
    p = g.proyecto
    return {"codigo": p.codigo, "proyecto": p.nombre, "unidad": p.unidad.nombre, "estado": p.estado.nombre if p.estado_id else "",
            "tipo_elemento": g.tipo_elemento.nombre, "nombre": g.nombre}


@login_required
def exportar_geojson(request):
    datos = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": json.loads(g.geom.geojson), "properties": _propiedades(g)}
        for g in _geometrias_exportables(request)]}
    respuesta = HttpResponse(json.dumps(datos, ensure_ascii=False), content_type="application/geo+json")
    respuesta["Content-Disposition"] = f'attachment; filename="gestion-rh-{date.today():%Y-%m-%d}.geojson"'
    return respuesta


@login_required
def exportar_kml(request):
    marcas = []
    for g in _geometrias_exportables(request):
        p = _propiedades(g)
        extendidos = "".join(f'<Data name="{escape(k)}"><value>{escape(str(v))}</value></Data>' for k, v in p.items())
        nombre = escape(f"{p['codigo']} – {p['nombre'] or p['tipo_elemento']}")
        marcas.append(f"<Placemark><name>{nombre}</name><ExtendedData>{extendidos}</ExtendedData>{g.geom.kml}</Placemark>")
    kml = ('<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           f"<name>Gestión RH – {date.today():%d/%m/%Y}</name>{''.join(marcas)}</Document></kml>")
    respuesta = HttpResponse(kml, content_type="application/vnd.google-earth.kml+xml")
    respuesta["Content-Disposition"] = f'attachment; filename="gestion-rh-{date.today():%Y-%m-%d}.kml"'
    return respuesta
