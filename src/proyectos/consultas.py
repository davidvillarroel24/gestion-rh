"""
Consultas reutilizables (visor, reportes, exportaciones).

Los totales se calculan con subconsultas por proyecto: así un proyecto en
varios municipios nunca multiplica su monto al filtrar o agrupar (D10).
"""

from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from core import alcance

from .models import Avance, Desembolso, Financiamiento, Proyecto

DINERO = DecimalField(max_digits=16, decimal_places=2)


def _suma(qs, agrupar_por, campo):
    total = qs.values(agrupar_por).annotate(t=Sum(campo)).values("t")[:1]
    return Coalesce(Subquery(total, output_field=DINERO), Value(0, output_field=DINERO))


def con_totales(qs):
    """Agrega total_comprometido, total_desembolsado y ultimo_avance_fisico a un queryset de proyectos."""
    financiamientos = Financiamiento.objects.filter(proyecto=OuterRef("pk"))
    desembolsos = Desembolso.objects.filter(financiamiento__proyecto=OuterRef("pk"))
    ultimo_avance = Avance.objects.filter(proyecto=OuterRef("pk")).order_by("-fecha").values("fisico_pct")[:1]
    return qs.annotate(
        total_comprometido=_suma(financiamientos, "proyecto", "monto_comprometido"),
        total_desembolsado=_suma(desembolsos, "financiamiento__proyecto", "monto"),
        ultimo_avance_fisico=Subquery(ultimo_avance),
    )


def visibles(usuario):
    return alcance.filtrar(Proyecto.objects.vigentes(), usuario, "unidad", "municipios")


def filtrar(qs, parametros):
    """Filtros comunes del visor/reportes: unidad, estado, municipio, gestion, q (texto)."""
    if parametros.get("unidad"):
        qs = qs.filter(unidad_id=parametros["unidad"])
    if parametros.get("estado"):
        qs = qs.filter(estado_id=parametros["estado"])
    if parametros.get("municipio"):
        qs = qs.filter(municipios=parametros["municipio"])
    if parametros.get("gestion"):
        qs = qs.filter(gestion=parametros["gestion"])
    if parametros.get("q"):
        from django.db.models import Q

        q = parametros["q"].strip()
        qs = qs.filter(Q(nombre__icontains=q) | Q(codigo__icontains=q) | Q(comunidad__icontains=q) | Q(sisin__icontains=q))
    return qs.distinct()
