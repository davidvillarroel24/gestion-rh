"""Administración de Django para licencias: solo respaldo del superusuario. El área trabaja en /licencias/."""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from core.admin import CatalogoAdmin

from .models import AOP, Categoria, ConfiguracionLicencias, Equivalencia, Feriado, TipoDocumentoAmbiental, TipoIngreso, Tramite

for modelo in (TipoDocumentoAmbiental, Categoria, TipoIngreso):
    admin.site.register(modelo, CatalogoAdmin)


@admin.register(AOP)
class AOPAdmin(SimpleHistoryAdmin):
    list_display = ["nombre", "representante", "consultor", "eliminado"]
    search_fields = ["nombre"]
    filter_horizontal = ["municipios"]
    raw_id_fields = ["representante", "consultor"]


@admin.register(Tramite)
class TramiteAdmin(SimpleHistoryAdmin):
    list_display = ["id", "numero", "aop", "tipo_documento", "fecha_presentacion", "categoria", "eliminado"]
    list_filter = ["tipo_documento", "categoria", "eliminado"]
    search_fields = ["numero", "numero_asignado", "aop__nombre"]
    raw_id_fields = ["aop", "proyecto"]


admin.site.register(Equivalencia, SimpleHistoryAdmin)
admin.site.register(Feriado)
admin.site.register(ConfiguracionLicencias, SimpleHistoryAdmin)
