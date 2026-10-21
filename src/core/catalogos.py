"""
API para catálogos que crecen con el uso (D18): los selectores de los
formularios buscan valores y, si el usuario tiene permiso, crean uno nuevo
sin salir del formulario.

    GET  /catalogos/<catalogo>/?q=texto        -> [{"id", "nombre"}]
    POST /catalogos/<catalogo>/  nombre=...     -> 201 creado
                                                -> 200 ya existía (mismo valor normalizado)
                                                -> 409 hay parecidos (reenviar con confirmar=1 para crearlo igual)

Catálogos por unidad (programa, tipo de proyecto, tipo de elemento) piden
además ?unidad=<id> (GET) o "unidad" en el cuerpo (POST).
"""

import json

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_http_methods

from . import alcance
from .models import TipoDocumento, TipoEvento, TipoFuente, Unidad
from .texto import normalizar

CATALOGOS = {
    "unidades": Unidad,
    "tipos-fuente": TipoFuente,
    "tipos-documento": TipoDocumento,
    "tipos-evento": TipoEvento,
}

LIMITE_RESULTADOS = 20


def _datos(obj):
    return {"id": obj.pk, "nombre": obj.nombre}


def _permiso(modelo, accion):
    return f"{modelo._meta.app_label}.{accion}_{modelo._meta.model_name}"


def _ambito(modelo, datos):
    """Para catálogos por unidad: {"unidad_id": ...} leído de la petición (None si falta)."""
    ambito = {}
    for campo in modelo.campos_ambito:
        try:
            ambito[f"{campo}_id"] = int(datos.get(campo))
        except (TypeError, ValueError):
            return None
    return ambito


@login_required
@require_http_methods(["GET", "POST"])
def catalogo(request, nombre):
    modelo = CATALOGOS.get(nombre)
    if modelo is None:
        raise Http404("Catálogo desconocido")

    if request.method == "GET":
        if not request.user.has_perm(_permiso(modelo, "view")):
            return JsonResponse({"error": "Sin permiso"}, status=403)
        ambito = _ambito(modelo, request.GET)
        if ambito is None:
            return JsonResponse({"error": f"Falta: {', '.join(modelo.campos_ambito)}"}, status=400)
        qs = modelo.objects.filter(activo=True, **ambito)
        q = normalizar(request.GET.get("q", ""))
        if q:
            qs = qs.filter(clave__contains=q)
        return JsonResponse([_datos(o) for o in qs[:LIMITE_RESULTADOS]], safe=False)

    if not request.user.has_perm(_permiso(modelo, "add")):
        return JsonResponse({"error": "Su rol no permite crear valores en este catálogo."}, status=403)

    if request.content_type == "application/json":
        try:
            datos = json.loads(request.body or "{}")
        except ValueError:
            return JsonResponse({"error": "JSON inválido."}, status=400)
    else:
        datos = request.POST
    ambito = _ambito(modelo, datos)
    if ambito is None:
        return JsonResponse({"error": f"Falta: {', '.join(modelo.campos_ambito)}"}, status=400)
    if "unidad_id" in ambito and not alcance.unidades_visibles(request.user).filter(pk=ambito["unidad_id"]).exists():
        return JsonResponse({"error": "La unidad no está en su alcance."}, status=403)
    texto = " ".join(str(datos.get("nombre", "")).split())
    if not normalizar(texto):
        return JsonResponse({"error": "El nombre no puede quedar vacío."}, status=400)

    existente = modelo.objects.filter(clave=normalizar(texto), **ambito).first()
    if existente:
        return JsonResponse({**_datos(existente), "existente": True}, status=200)

    if str(datos.get("confirmar", "")) not in ("1", "true", "True"):
        parecidos = modelo.parecidos(texto, **ambito)
        if parecidos:
            return JsonResponse({"parecidos": [_datos(p) for p in parecidos]}, status=409)

    obj = modelo.objects.create(nombre=texto, **ambito)
    return JsonResponse(_datos(obj), status=201)
