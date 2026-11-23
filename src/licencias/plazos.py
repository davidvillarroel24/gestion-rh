"""Vencimiento de un trámite según los días de su categoría (§11.5)."""

from datetime import timedelta

from .models import Feriado


def sumar_dias(inicio, dias, habiles, feriados=None):
    """inicio + dias; en días hábiles se saltan sábados, domingos y feriados."""
    if not habiles:
        return inicio + timedelta(days=dias)
    if feriados is None:
        feriados = set(Feriado.objects.values_list("fecha", flat=True))
    fecha, contados = inicio, 0
    while contados < dias:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5 and fecha not in feriados:
            contados += 1
    return fecha


def vencimiento(tramite, feriados=None):
    """Fecha en que vence, o None si su categoría no tiene días o falta la fecha de inicio."""
    categoria = tramite.categoria
    if categoria is None or categoria.dias is None:
        return None
    inicio = tramite.fecha_resultado if categoria.contar_desde == categoria.RESULTADO else tramite.fecha_presentacion
    if inicio is None:
        return None
    return sumar_dias(inicio, categoria.dias, categoria.dias_habiles, feriados)
