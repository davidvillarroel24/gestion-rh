"""
Administración de proyectos: interfaz provisoria hasta que exista el visor (Fase 5).

- Todo pasa por core.alcance: cada usuario ve y elige solo proyectos de sus
  unidades/municipios.
- Las geometrías se dibujan a mano sobre OpenStreetMap.
- Al crear un registro se guarda quién lo hizo (creado_por, registrado_por…).
"""

from django.contrib import admin
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.forms.widgets import OSMWidget
from django.urls import reverse
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from core import alcance
from core.admin import CatalogoAdmin

from .models import (
    Avance, Desagregacion, Desembolso, DetalleForestacion, DetalleResiduos, Documento, EstadoProyecto, Evento,
    Financiamiento, Geometria, Indicador, Material, Medicion, Programa, Proposito, Proyecto, ProyectoMaterial,
    TipoElemento, TipoPlanta, TipoProyecto,
)

MAPA = {gis_models.GeometryField: {"widget": OSMWidget(attrs={"default_lat": -17.39, "default_lon": -66.16, "default_zoom": 8})}}

# Campo "autor" de cada modelo que se completa solo al crear.
AUTOR = {Proyecto: "creado_por", Desembolso: "registrado_por", Medicion: "registrado_por",
         Evento: "usuario", Documento: "subido_por"}


def proyectos_visibles(usuario):
    return alcance.filtrar(Proyecto.objects.vigentes(), usuario, "unidad", "municipios")


def _completar_autor(obj, usuario):
    campo = AUTOR.get(type(obj))
    if campo and getattr(obj, f"{campo}_id") is None:
        setattr(obj, campo, usuario)


class AlcanceMixin:
    """Limita listados y selectores al alcance del usuario."""

    ruta_proyecto = "proyecto"  # cómo llegar al proyecto desde este modelo

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.ruta_proyecto:
            return qs.filter(**{f"{self.ruta_proyecto}__in": proyectos_visibles(request.user)})
        return qs

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "proyecto":
            kwargs["queryset"] = proyectos_visibles(request.user)
        elif db_field.name == "unidad":
            kwargs["queryset"] = alcance.unidades_visibles(request.user)
        elif db_field.name == "financiamiento":
            kwargs["queryset"] = Financiamiento.objects.filter(proyecto__in=proyectos_visibles(request.user))
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "municipios":
            kwargs["queryset"] = alcance.municipios_visibles(request.user)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        _completar_autor(obj, request.user)
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        for obj in formset.save(commit=False):
            _completar_autor(obj, request.user)
            obj.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()


# ---------------------------------------------------------------- catálogos

for modelo in (EstadoProyecto, Indicador, Desagregacion, Material, Proposito, TipoPlanta):
    admin.site.register(modelo, CatalogoAdmin)


class CatalogoPorUnidadAdmin(AlcanceMixin, CatalogoAdmin):
    ruta_proyecto = None
    list_display = ["nombre", "unidad", "activo"]
    list_filter = ["unidad", "activo"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(unidad__in=alcance.unidades_visibles(request.user))


admin.site.register(Programa, CatalogoPorUnidadAdmin)
admin.site.register(TipoProyecto, CatalogoPorUnidadAdmin)


@admin.register(TipoElemento)
class TipoElementoAdmin(CatalogoPorUnidadAdmin):
    list_display = ["nombre", "unidad", "tipo_geometria", "activo"]


# ---------------------------------------------------------------- proyecto


class FinanciamientoInline(admin.TabularInline):
    model = Financiamiento
    extra = 0
    show_change_link = True  # los desembolsos se cargan dentro de cada financiamiento
    fields = ["entidad", "monto_comprometido", "desembolsado"]
    readonly_fields = ["desembolsado"]
    autocomplete_fields = ["entidad"]


class AvanceInline(admin.TabularInline):
    model = Avance
    extra = 0


class MaterialInline(admin.TabularInline):
    model = ProyectoMaterial
    extra = 0


class MedicionInline(admin.TabularInline):
    model = Medicion
    extra = 0
    fields = ["indicador", "desagregacion", "momento", "fecha", "valor", "fuente"]


class GeometriaInline(admin.StackedInline):
    model = Geometria
    extra = 0
    formfield_overrides = MAPA

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "tipo_elemento":
            kwargs["queryset"] = TipoElemento.objects.filter(unidad__in=alcance.unidades_visibles(request.user), activo=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class EventoInline(admin.TabularInline):
    model = Evento
    extra = 0
    fields = ["fecha", "tipo", "descripcion", "estado_nuevo"]


class DocumentoInline(admin.TabularInline):
    model = Documento
    extra = 0
    fields = ["tipo", "nombre", "archivo"]


class DetalleResiduosInline(admin.StackedInline):
    model = DetalleResiduos
    max_num = 1
    extra = 0


class DetalleForestacionInline(admin.StackedInline):
    model = DetalleForestacion
    max_num = 1
    extra = 0


@admin.register(Proyecto)
class ProyectoAdmin(AlcanceMixin, SimpleHistoryAdmin):
    ruta_proyecto = None
    list_display = ["codigo", "nombre", "unidad", "estado", "gestion", "lista_municipios"]
    list_filter = ["unidad", "estado", "gestion", "municipios__region", "municipios__provincia"]
    search_fields = ["codigo", "nombre", "sisin", "comunidad"]
    filter_horizontal = ["municipios"]
    autocomplete_fields = ["entidad_ejecutora"]
    readonly_fields = ["codigo", "estado", "costo_total", "desembolsado", "saldo_por_desembolsar",
                       "avance_financiero_pct", "avance_fisico_pct", "plazo"]
    fieldsets = [
        (None, {"fields": ["codigo", "unidad", "nombre", "programa", "tipo", "entidad_ejecutora", "sisin", "gestion"]}),
        ("Ubicación", {"fields": ["municipios", "comunidad"],
                       "description": "Si se dejan vacíos los municipios, se completan con los que tocan sus geometrías."}),
        ("Plazos", {"fields": ["fecha_orden_proceder", "fecha_conclusion", "plazo"]}),
        ("Situación (calculada)", {"fields": ["estado", "costo_total", "desembolsado", "saldo_por_desembolsar",
                                              "avance_financiero_pct", "avance_fisico_pct"],
                                   "description": "El estado lo cambia la bitácora; los montos salen del financiamiento y los desembolsos."}),
        (None, {"fields": ["observaciones"]}),
    ]
    inlines = [FinanciamientoInline, AvanceInline, MaterialInline, MedicionInline, GeometriaInline,
               EventoInline, DocumentoInline, DetalleResiduosInline, DetalleForestacionInline]

    def get_queryset(self, request):
        return proyectos_visibles(request.user).prefetch_related("municipios")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name in ("programa", "tipo"):
            kwargs["queryset"] = db_field.related_model.objects.filter(
                unidad__in=alcance.unidades_visibles(request.user), activo=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        proyecto = form.instance
        if not proyecto.municipios.exists():
            for geometria in proyecto.geometrias.all():
                proyecto.municipios.add(*geometria.municipios_que_toca())

    @admin.display(description="Municipios")
    def lista_municipios(self, obj):
        return ", ".join(m.nombre for m in obj.municipios.all())

    @admin.display(description="Avance financiero (%)")
    def avance_financiero_pct(self, obj):
        return obj.avance_financiero if obj.pk else None

    @admin.display(description="Avance físico (%)")
    def avance_fisico_pct(self, obj):
        return obj.avance_fisico if obj.pk else None

    @admin.display(description="Plazo (días)")
    def plazo(self, obj):
        return obj.plazo_dias

    @admin.display(description="Costo total")
    def costo_total(self, obj):
        return obj.costo_total if obj.pk else None

    @admin.display(description="Desembolsado")
    def desembolsado(self, obj):
        return obj.desembolsado if obj.pk else None

    @admin.display(description="Saldo por desembolsar")
    def saldo_por_desembolsar(self, obj):
        return obj.saldo_por_desembolsar if obj.pk else None


# ---------------------------------------------------------------- registros con su propia página
# Para quien no edita el proyecto completo (ej. encargado municipal: mediciones y bitácora).


class DesembolsoInline(admin.TabularInline):
    model = Desembolso
    extra = 0
    fields = ["fecha", "monto", "comprobante", "descripcion", "excede_confirmado"]


@admin.register(Financiamiento)
class FinanciamientoAdmin(AlcanceMixin, SimpleHistoryAdmin):
    list_display = ["proyecto", "entidad", "monto_comprometido", "desembolsado"]
    autocomplete_fields = ["entidad"]
    inlines = [DesembolsoInline]


@admin.register(Desembolso)
class DesembolsoAdmin(AlcanceMixin, SimpleHistoryAdmin):
    ruta_proyecto = "financiamiento__proyecto"
    list_display = ["fecha", "financiamiento", "monto", "comprobante"]
    list_filter = ["fecha"]


@admin.register(Medicion)
class MedicionAdmin(AlcanceMixin, SimpleHistoryAdmin):
    list_display = ["proyecto", "indicador", "desagregacion", "momento", "fecha", "valor"]
    list_filter = ["momento", "indicador"]
    search_fields = ["proyecto__codigo", "proyecto__nombre"]


@admin.register(Evento)
class EventoAdmin(AlcanceMixin, SimpleHistoryAdmin):
    list_display = ["fecha", "proyecto", "tipo", "estado_nuevo", "usuario"]
    list_filter = ["tipo", "estado_nuevo"]
    search_fields = ["proyecto__codigo", "proyecto__nombre", "descripcion"]


@admin.register(Documento)
class DocumentoAdmin(AlcanceMixin, SimpleHistoryAdmin):
    list_display = ["__str__", "proyecto", "tipo", "subido_en", "descargar"]
    search_fields = ["nombre", "proyecto__codigo", "proyecto__nombre"]

    @admin.display(description="Archivo")
    def descargar(self, obj):
        return format_html('<a href="{}">Descargar</a>', reverse("proyectos:descargar_documento", args=[obj.pk]))


@admin.register(Geometria)
class GeometriaAdmin(AlcanceMixin, SimpleHistoryAdmin):
    list_display = ["__str__", "proyecto", "tipo_elemento"]
    list_filter = ["tipo_elemento"]
    formfield_overrides = MAPA
