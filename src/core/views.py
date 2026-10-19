from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

from . import alcance


@login_required
def inicio(request):
    usuario = request.user
    return render(request, "core/inicio.html", {
        "roles": sorted(alcance.nombres_de_roles(usuario)),
        "ve_todo": alcance.ve_todo(usuario),
        "unidades": alcance.unidades_visibles(usuario),
        "municipios": alcance.municipios_visibles(usuario),
    })


def salud(request):
    """Lo usa el healthcheck de Docker: responde 200 solo si la base y PostGIS contestan."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT postgis_version()")
            postgis = cursor.fetchone()[0]
    except Exception:
        return JsonResponse({"estado": "error", "detalle": "sin conexión a la base"}, status=503)
    return JsonResponse({"estado": "ok", "postgis": postgis})
