"""Páginas del módulo de licencias (sin mapa, D31)."""

import io
from datetime import date

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import ProtectedError
from django.core.paginator import Paginator
from django.forms import modelformset_factory
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from core import alcance

from territorio.models import Municipio

from . import tabla
from .models import COLUMNAS, Categoria, ConfiguracionLicencias, Feriado, TipoDocumentoAmbiental, TipoIngreso, Tramite

POR_PAGINA = 50
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _solo_licencias(usuario):
    if not alcance.ve_licencias(usuario):
        raise PermissionDenied


def _solo_administrador(usuario):
    if not alcance.administra_licencias(usuario):
        raise PermissionDenied


def _fecha(campo, **kwargs):
    formulario = campo.formfield(**kwargs)
    if isinstance(formulario, forms.DateField):
        formulario.widget = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    return formulario


def _mostrar(valor):
    if valor is None:
        return ""
    if isinstance(valor, date):
        return f"{valor:%d/%m/%Y}"
    return valor


def _parametros_sin(request, *claves):
    """La URL actual sin algunas claves (para armar enlaces de orden y de página)."""
    datos = request.GET.copy()
    for clave in claves:
        datos.pop(clave, None)
    return datos.urlencode()


@login_required
def inicio(request):
    """Tabla principal de trámites (etapa 11.2)."""
    usuario = request.user
    _solo_licencias(usuario)
    qs, pestana = tabla.consulta(usuario, request.GET)
    pagina = Paginator(qs, POR_PAGINA).get_page(request.GET.get("pagina"))
    columnas = tabla.columnas_visibles(usuario)
    ctx = tabla.Contexto()
    permitidas = tabla.columnas_permitidas(usuario)
    vigentes = Tramite.objects.filter(eliminado=False)
    cantidades = {"tramites": vigentes.exclude(tipo_documento__es_consulta_categoria=True).count(),
                  "consultas": vigentes.filter(tipo_documento__es_consulta_categoria=True).count(),
                  "papelera": Tramite.objects.filter(eliminado=True).count()}
    pestanas = [(clave, nombre, cantidades[clave]) for clave, nombre in tabla.PESTANAS
                if clave != "papelera" or alcance.administra_licencias(usuario)]
    orden = request.GET.get("orden", "")
    return render(request, "licencias/tabla.html", {
        "pestanas": pestanas, "pestana": pestana, "pagina": pagina, "total": pagina.paginator.count,
        "encabezados": [(c, tabla.TITULOS[c], c in tabla.ORDEN) for c in columnas],
        "filas": [(t, estado, [_mostrar(v) for v in valores]) for t, estado, valores in tabla.filas(pagina.object_list, columnas, ctx)],
        "orden": orden, "orden_campo": orden.lstrip("-"), "orden_desc": orden.startswith("-"),
        "sin_orden": _parametros_sin(request, "orden", "pagina"), "sin_pagina": _parametros_sin(request, "pagina"),
        "parametros": request.GET.urlencode(),
        "columnas_permitidas": [(c, tabla.TITULOS[c], c in columnas) for c in permitidas],
        "filtros": request.GET, "puede": {f: tabla.FILTRO_COLUMNA[f] in permitidas for f in tabla.FILTRO_COLUMNA},
        "municipios": Municipio.objects.order_by("nombre"),
        "tipos_documento": TipoDocumentoAmbiental.objects.order_by("nombre"),
        "categorias": Categoria.objects.order_by("nombre"), "tipos_ingreso": TipoIngreso.objects.order_by("nombre"),
        "tecnicos": vigentes.exclude(tecnico="").values_list("tecnico", flat=True).distinct().order_by("tecnico"),
        "legales": vigentes.exclude(legal="").values_list("legal", flat=True).distinct().order_by("legal"),
    })


@login_required
@require_POST
def columnas(request):
    """Guarda las columnas que el usuario eligió ver (solo entre las que permite su rol)."""
    _solo_licencias(request.user)
    tabla.guardar_columnas(request.user, request.POST.getlist("columnas"))
    volver = request.POST.get("volver", "")
    if not url_has_allowed_host_and_scheme(volver, allowed_hosts={request.get_host()}):
        volver = reverse("licencias:inicio")
    return redirect(volver)


@login_required
def excel(request):
    """Lo filtrado en la tabla, con las mismas columnas visibles (todas las páginas)."""
    usuario = request.user
    _solo_licencias(usuario)
    qs, pestana = tabla.consulta(usuario, request.GET)
    columnas = tabla.columnas_visibles(usuario)
    ctx = tabla.Contexto()
    libro = Workbook()
    hoja = libro.active
    hoja.title = dict(tabla.PESTANAS)[pestana][:31]
    hoja.append([tabla.TITULOS[c] for c in columnas])
    for celda in hoja[1]:
        celda.font = Font(bold=True)
        celda.fill = PatternFill("solid", fgColor="D1E7DD")
    rojo, amarillo = PatternFill("solid", fgColor="F8D7DA"), PatternFill("solid", fgColor="FFF3CD")
    for _, estado, valores in tabla.filas(qs, columnas, ctx):
        hoja.append(valores)
        if estado:
            for celda in hoja[hoja.max_row]:
                celda.fill = rojo if estado == "vencido" else amarillo
    for j, c in enumerate(columnas, start=1):
        hoja.column_dimensions[hoja.cell(row=1, column=j).column_letter].width = 14 if c not in ("aop", "observaciones") else 45
        for fila in hoja.iter_rows(min_row=2, min_col=j, max_col=j):
            if isinstance(fila[0].value, date):
                fila[0].number_format = "DD/MM/YYYY"
    hoja.freeze_panes = "A2"
    salida = io.BytesIO()
    libro.save(salida)
    respuesta = HttpResponse(salida.getvalue(), content_type=XLSX)
    respuesta["Content-Disposition"] = f'attachment; filename="licencias-{pestana}-{date.today():%Y-%m-%d}.xlsx"'
    return respuesta


# ---------------------------------------------------------------- configuración (Administrador de licencias)

# clave -> (título, modelo, campos, ayuda)
LISTAS = {
    "categorias": ("Categorías y sus días", Categoria, ["nombre", "dias", "contar_desde", "dias_habiles", "es_final", "activo"],
                   "Lista libre del área. «Días» vacío = sin alerta. El vencimiento se cuenta desde la fecha elegida, "
                   "en días calendario o hábiles (sin fines de semana ni feriados)."),
    "tipos_documento": ("Tipos de documento", TipoDocumentoAmbiental,
                        ["nombre", "sigla", "periodicidad", "es_consulta_categoria", "activo"],
                        "Anual = la AOP debe presentarlo cada gestión (IMA). «Es consulta de categoría» los muestra en esa pestaña."),
    "tipos_ingreso": ("Tipos de ingreso", TipoIngreso, ["nombre", "activo"], ""),
    "feriados": ("Feriados", Feriado, ["fecha", "nombre"], "Solo para las categorías que cuentan días hábiles."),
}
SECCIONES = [(k, v[0]) for k, v in LISTAS.items()] + [("general", "General y columnas")]


class GeneralForm(forms.ModelForm):
    columnas_funcionario = forms.MultipleChoiceField(
        label="Columnas que ve el funcionario", choices=COLUMNAS, widget=forms.CheckboxSelectMultiple, required=False,
        help_text="El Administrador de licencias ve siempre todas. Al principio son las mismas de la app anterior.")

    class Meta:
        model = ConfiguracionLicencias
        fields = ["dias_aviso", "columnas_funcionario"]


@login_required
def configuracion(request):
    _solo_administrador(request.user)
    seccion = request.GET.get("seccion", "categorias")
    if seccion not in dict(SECCIONES):
        seccion = "categorias"
    datos = request.POST if request.method == "POST" else None
    volver = f"{reverse('licencias:configuracion')}?seccion={seccion}"
    contexto = {"secciones": SECCIONES, "seccion": seccion, "titulo_seccion": dict(SECCIONES)[seccion]}

    if seccion == "general":
        form = GeneralForm(datos, instance=ConfiguracionLicencias.actual())
        if datos is not None and form.is_valid():
            form.save()
            messages.success(request, "Configuración guardada.")
            return redirect(volver)
        contexto["form"] = form
    else:
        titulo, modelo, campos, ayuda = LISTAS[seccion]
        clase = modelformset_factory(modelo, fields=campos, extra=1, can_delete=True, formfield_callback=_fecha)
        formset = clase(datos, queryset=modelo.objects.all(), prefix=seccion)
        if datos is not None and formset.is_valid():
            try:
                with transaction.atomic():
                    formset.save()
            except ProtectedError:
                messages.error(request, "No se puede borrar un valor que ya usan trámites: desactívelo (columna «Activo»).")
            else:
                messages.success(request, f"{titulo}: cambios guardados.")
                return redirect(volver)
        contexto.update(formset=formset, ayuda=ayuda)
    return render(request, "licencias/configuracion.html", contexto)
