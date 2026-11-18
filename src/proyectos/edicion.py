"""
Edición del proyecto dentro del sistema (sin pasar por /admin): una página con
pestañas que reúne lo mismo que la administración — datos generales, ubicación,
financiamiento y desembolsos, avance, materiales, mediciones, bitácora,
documentos, geometrías, detalle de la unidad e historial.

Se abre sola (/proyectos/<id>/editar/) o dentro del visor, en lugar del mapa
(?incrustado=1). Cada pestaña se guarda por separado y respeta los permisos del
rol: lo que el usuario no puede modificar se muestra sin edición.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.forms import inlineformset_factory, modelformset_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin

from core import alcance
from core.models import Entidad

from .models import (
    Avance, Desembolso, DetalleForestacion, DetalleResiduos, Documento, Evento, Financiamiento, Geometria, Medicion,
    Programa, Proyecto, ProyectoMaterial, TipoElemento, TipoProyecto,
)

# Campo "autor" que se completa solo al crear (igual que en la administración).
AUTOR = {Proyecto: "creado_por", Desembolso: "registrado_por", Medicion: "registrado_por",
         Evento: "usuario", Documento: "subido_por"}


def _widget_fecha(campo, **kwargs):
    formulario = campo.formfield(**kwargs)
    if isinstance(formulario, forms.DateField):
        formulario.widget = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    return formulario


# ---------------------------------------------------------------- datos generales


class ProyectoForm(forms.ModelForm):
    class Meta:
        model = Proyecto
        fields = ["unidad", "nombre", "programa", "tipo", "entidad_ejecutora", "sisin", "gestion",
                  "municipios", "comunidad", "fecha_orden_proceder", "fecha_conclusion", "observaciones"]
        formfield_callback = _widget_fecha
        widgets = {"municipios": forms.CheckboxSelectMultiple, "observaciones": forms.Textarea(attrs={"rows": 3}),
                   "nombre": forms.TextInput(attrs={"size": 80})}
        help_texts = {"municipios": "Si se deja vacío, se completa con los municipios que tocan sus geometrías."}

    def __init__(self, *args, usuario=None, **kwargs):
        super().__init__(*args, **kwargs)
        unidades = alcance.unidades_visibles(usuario)
        self.fields["unidad"].queryset = unidades.filter(activo=True)
        self.fields["programa"].queryset = Programa.objects.filter(unidad__in=unidades).select_related("unidad")
        self.fields["tipo"].queryset = TipoProyecto.objects.filter(unidad__in=unidades).select_related("unidad")
        self.fields["entidad_ejecutora"].queryset = Entidad.objects.order_by("nombre")
        self.fields["municipios"].queryset = alcance.municipios_visibles(usuario).order_by("nombre")
        for campo in ("programa", "tipo"):  # "Mi Riego (Riego)": el script del formulario deja solo los de la unidad
            self.fields[campo].label_from_instance = lambda o: f"{o.nombre} ({o.unidad})"


# ---------------------------------------------------------------- tablas que cuelgan del proyecto


def _formset(modelo, campos, puede_agregar, puede_borrar, widgets=None):
    return inlineformset_factory(Proyecto, modelo, fields=campos, extra=1 if puede_agregar else 0,
                                 can_delete=puede_borrar, formfield_callback=_widget_fecha, widgets=widgets or {})


TEXTO_CORTO = {"descripcion": forms.Textarea(attrs={"rows": 2})}

# clave -> (título, modelo, campos, widgets). El orden es el de las pestañas.
TABLAS = {
    "financiamiento": ("Financiamiento", Financiamiento, ["entidad", "monto_comprometido"], None),
    "avances": ("Avance físico", Avance, ["fecha", "fisico_pct", "observacion"], None),
    "materiales": ("Materiales", ProyectoMaterial, ["material", "cantidad"], None),
    "mediciones": ("Mediciones", Medicion, ["indicador", "desagregacion", "momento", "fecha", "valor", "fuente"], None),
    "bitacora": ("Bitácora", Evento, ["fecha", "tipo", "descripcion", "estado_nuevo"], TEXTO_CORTO),
    "documentos": ("Documentos", Documento, ["tipo", "nombre", "archivo"], None),
    "geometrias": ("Geometrías", Geometria, ["tipo_elemento", "nombre"], None),
}


def _permisos(usuario, modelo):
    etiqueta = f"{modelo._meta.app_label}.%s_{modelo._meta.model_name}"
    return {accion: usuario.has_perm(etiqueta % accion) for accion in ("view", "add", "change", "delete")}


def _completar_autor(obj, usuario):
    campo = AUTOR.get(type(obj))
    if campo and getattr(obj, f"{campo}_id") is None:
        setattr(obj, campo, usuario)


def _guardar_formset(formset, usuario):
    for obj in formset.save(commit=False):
        _completar_autor(obj, usuario)
        obj.save()
    for obj in formset.deleted_objects:
        obj.delete()


def _desembolsos(proyecto, usuario, datos=None):
    permisos = _permisos(usuario, Desembolso)
    clase = modelformset_factory(Desembolso, fields=["financiamiento", "fecha", "monto", "comprobante", "descripcion",
                                                     "excede_confirmado"],
                                 extra=1 if permisos["add"] else 0, can_delete=permisos["delete"],
                                 formfield_callback=_widget_fecha)
    formset = clase(datos, prefix="desembolsos",
                    queryset=Desembolso.objects.filter(financiamiento__proyecto=proyecto).order_by("fecha", "id"))
    for f in formset.forms + [formset.empty_form]:
        f.fields["financiamiento"].queryset = proyecto.financiamientos.select_related("entidad")
        f.fields["financiamiento"].label_from_instance = lambda x: x.entidad.nombre
    return formset, permisos


# ---------------------------------------------------------------- vistas


def _proyecto_visible(usuario, pk):
    proyecto = alcance.filtrar(Proyecto.objects.vigentes(), usuario, "unidad", "municipios").filter(pk=pk).first()
    if proyecto is None:
        raise Http404
    return proyecto


def _detalle(proyecto):
    """Modelo de detalle según la unidad (residuos sólidos o forestación), si corresponde."""
    clave = proyecto.unidad.clave
    if clave.startswith("residuos"):
        return DetalleResiduos, ["botadero", "licencia", "riesgo", "ton_urbano", "ton_rural"]
    if clave.startswith("forestacion"):
        return DetalleForestacion, ["proposito", "campania", "plantines", "tipo_planta"]
    return None, None


def secciones_de(proyecto):
    lista = [("general", "Datos generales")] + [(k, v[0]) for k, v in TABLAS.items()]
    if _detalle(proyecto)[0]:
        lista.append(("detalle", "Detalle de " + proyecto.unidad.nombre.lower()))
    return lista + [("historial", "Historial")]


def _url(nombre, *args, incrustado=False, seccion=None):
    url = reverse(nombre, args=args)
    params = [p for p in (f"seccion={seccion}" if seccion else "", "incrustado=1" if incrustado else "") if p]
    return url + ("?" + "&".join(params) if params else "")


def _base(incrustado):
    return "proyectos/base_incrustada.html" if incrustado else "pagina.html"


# Se muestran dentro del visor (iframe del mismo sitio); el resto del sistema sigue con X-Frame-Options: DENY.
@xframe_options_sameorigin
@login_required
def nuevo(request):
    if not request.user.has_perm("proyectos.add_proyecto"):
        raise PermissionDenied
    incrustado = request.GET.get("incrustado") == "1"
    form = ProyectoForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            proyecto = form.save(commit=False)
            proyecto.creado_por = request.user
            proyecto.save()
            form.save_m2m()
        messages.success(request, f"Proyecto {proyecto.codigo} creado. Complete el resto en las pestañas.")
        return redirect(_url("proyectos:editar", proyecto.pk, incrustado=incrustado))
    return render(request, "proyectos/editar.html", {"base": _base(incrustado), "incrustado": incrustado, "form": form,
                                                     "proyecto": None, "seccion": "general", "puede_editar": True})


@xframe_options_sameorigin
@login_required
def editar(request, pk):
    usuario = request.user
    proyecto = _proyecto_visible(usuario, pk)
    incrustado = request.GET.get("incrustado") == "1"
    secciones = secciones_de(proyecto)
    seccion = request.GET.get("seccion", "general")
    if seccion not in dict(secciones):
        seccion = "general"
    datos = request.POST if request.method == "POST" else None
    archivos = request.FILES if request.method == "POST" else None
    contexto = {"base": _base(incrustado), "incrustado": incrustado, "proyecto": proyecto, "secciones": secciones,
                "seccion": seccion, "titulo_seccion": dict(secciones)[seccion]}
    volver = _url("proyectos:editar", pk, incrustado=incrustado, seccion=seccion)

    if seccion == "general":
        puede = usuario.has_perm("proyectos.change_proyecto")
        form = ProyectoForm(datos, instance=proyecto, usuario=usuario)
        if datos is not None:
            if not puede:
                raise PermissionDenied
            if form.is_valid():
                with transaction.atomic():
                    form.save()
                    if not proyecto.municipios.exists():
                        for geometria in proyecto.geometrias.all():
                            proyecto.municipios.add(*geometria.municipios_que_toca())
                messages.success(request, "Datos generales guardados.")
                return redirect(volver)
        contexto.update(form=form, puede_editar=puede)

    elif seccion in TABLAS:
        _, modelo, campos, widgets = TABLAS[seccion]
        permisos = _permisos(usuario, modelo)
        # Las geometrías nuevas se dibujan en el mapa: acá solo se renombran, cambian de tipo o se eliminan.
        clase = _formset(modelo, campos, permisos["add"] and modelo is not Geometria, permisos["delete"], widgets)
        formset = clase(datos, archivos, instance=proyecto, prefix=seccion)
        if modelo is Geometria:
            for f in formset.forms + [formset.empty_form]:
                f.fields["tipo_elemento"].queryset = TipoElemento.objects.filter(unidad=proyecto.unidad)
        desembolsos, permisos_desembolsos = (_desembolsos(proyecto, usuario, datos) if seccion == "financiamiento"
                                             else (None, None))
        puede = permisos["add"] or permisos["change"] or permisos["delete"]
        if datos is not None:
            if not (puede or (permisos_desembolsos and any(permisos_desembolsos.values()))):
                raise PermissionDenied
            validos = formset.is_valid() and (desembolsos is None or desembolsos.is_valid())
            if validos:
                with transaction.atomic():
                    if puede:
                        _guardar_formset(formset, usuario)
                    if desembolsos is not None and (permisos_desembolsos["add"] or permisos_desembolsos["change"]):
                        _guardar_formset(desembolsos, usuario)
                messages.success(request, f"{contexto['titulo_seccion']}: cambios guardados.")
                return redirect(volver)
        contexto.update(formset=formset, puede_editar=puede, desembolsos=desembolsos,
                        puede_desembolsos=bool(permisos_desembolsos and (permisos_desembolsos["add"] or permisos_desembolsos["change"])),
                        es_geometria=modelo is Geometria, es_documento=modelo is Documento,
                        es_financiamiento=seccion == "financiamiento")

    elif seccion == "detalle":
        modelo, campos = _detalle(proyecto)
        permisos = _permisos(usuario, modelo)
        instancia = modelo.objects.filter(proyecto=proyecto).first()
        clase = forms.modelform_factory(modelo, fields=campos)
        form = clase(datos, instance=instancia)
        puede = permisos["change"] if instancia else permisos["add"]
        if datos is not None:
            if not puede:
                raise PermissionDenied
            if form.is_valid():
                obj = form.save(commit=False)
                obj.proyecto = proyecto
                obj.save()
                messages.success(request, "Detalle guardado.")
                return redirect(volver)
        contexto.update(form=form, puede_editar=puede)

    else:  # historial
        contexto["historial"] = historial(proyecto)

    if seccion == "general":
        contexto["resumen"] = {
            "Estado": proyecto.estado or "— (lo fija la bitácora)", "Costo total (Bs)": proyecto.costo_total,
            "Desembolsado (Bs)": proyecto.desembolsado, "Saldo por desembolsar (Bs)": proyecto.saldo_por_desembolsar,
            "Avance financiero (%)": proyecto.avance_financiero, "Avance físico (%)": proyecto.avance_fisico,
            "Plazo (días)": proyecto.plazo_dias,
        }
    return render(request, "proyectos/editar.html", contexto)


# ---------------------------------------------------------------- historial


def historial(proyecto, limite=150):
    """Cambios del proyecto y de todo lo que cuelga de él, del más reciente al más antiguo."""
    fuentes = [(proyecto.history.all(), "Datos generales")]
    for modelo, titulo in [(Financiamiento, "Financiamiento"), (Avance, "Avance físico"), (ProyectoMaterial, "Materiales"),
                           (Medicion, "Mediciones"), (Evento, "Bitácora"), (Documento, "Documentos"),
                           (Geometria, "Geometrías"), (DetalleResiduos, "Detalle"), (DetalleForestacion, "Detalle")]:
        if hasattr(modelo, "history"):
            fuentes.append((modelo.history.filter(proyecto_id=proyecto.pk), titulo))
    financiamientos = list(Financiamiento.history.filter(proyecto_id=proyecto.pk).values_list("id", flat=True).distinct())
    fuentes.append((Desembolso.history.filter(financiamiento_id__in=financiamientos), "Desembolsos"))

    registros = []
    for qs, titulo in fuentes:
        for r in qs.select_related("history_user").order_by("-history_date")[:limite]:
            registros.append((r, titulo))
    registros.sort(key=lambda x: x[0].history_date, reverse=True)

    filas = []
    for r, titulo in registros[:limite]:
        cambios = ""
        if r.history_type == "~":
            anterior = r.prev_record
            if anterior is not None:
                try:
                    delta = r.diff_against(anterior, excluded_fields=["geom"])
                    cambios = "; ".join(f"{c.field}: {c.old} → {c.new}" for c in delta.changes)
                except Exception:
                    cambios = ""
        filas.append({"fecha": r.history_date, "usuario": r.history_user, "seccion": titulo,
                      "accion": {"+": "Creado", "~": "Modificado", "-": "Eliminado"}[r.history_type],
                      "registro": str(r.instance),
                      "cambios": cambios})
    return filas
