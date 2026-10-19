from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render


def inicio(request):
    return render(request, "core/inicio.html")


def salud(request):
    """Lo usa el healthcheck de Docker: responde 200 solo si la base y PostGIS contestan."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT postgis_version()")
            postgis = cursor.fetchone()[0]
    except Exception:
        return JsonResponse({"estado": "error", "detalle": "sin conexión a la base"}, status=503)
    return JsonResponse({"estado": "ok", "postgis": postgis})
