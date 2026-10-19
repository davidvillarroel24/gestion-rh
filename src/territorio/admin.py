from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import Municipio, Provincia, Region
from .servicios import recalcular_agregados


@admin.register(Municipio)
class MunicipioAdmin(GISModelAdmin, SimpleHistoryAdmin):
    list_display = ["nombre", "codigo_ine", "provincia", "region", "es_tioc"]
    list_filter = ["region", "provincia", "es_tioc"]
    search_fields = ["nombre", "codigo_ine"]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Provincia/región derivan sus límites de los municipios.
        recalcular_agregados()


class AgregadoAdmin(GISModelAdmin):
    """Provincias y regiones: la geometría es derivada, solo lectura."""

    readonly_fields = ["geom"]
    search_fields = ["nombre"]

    @admin.display(description="Municipios")
    def cantidad_municipios(self, obj):
        return obj.municipios.count()


@admin.register(Provincia)
class ProvinciaAdmin(AgregadoAdmin):
    list_display = ["nombre", "codigo", "cantidad_municipios"]


@admin.register(Region)
class RegionAdmin(AgregadoAdmin):
    list_display = ["nombre", "cantidad_municipios"]
