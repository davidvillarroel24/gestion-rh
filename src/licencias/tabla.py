"""
Tabla principal de trámites (etapa 11.2): filtros, orden, columnas por rol y por
usuario, valores de cada celda y descarga en Excel. La usan la página y la exportación,
así lo que se descarga es exactamente lo que se ve.
"""

from datetime import date, timedelta

from django.db.models import Q

from core import alcance

from .models import COLUMNAS, ConfiguracionLicencias, Feriado, PreferenciaColumnas, Tramite
from .plazos import vencimiento

PESTANAS = [("tramites", "Trámites (IRAP)"), ("consultas", "Consultas de categoría"), ("papelera", "Papelera")]
TITULOS = dict(COLUMNAS)
# Orden por columna: clave de la tabla -> campo de la base (las calculadas no se ordenan).
ORDEN = {"id": "id", "numero": "numero", "numero_asignado": "numero_asignado", "fecha_presentacion": "fecha_presentacion",
         "aop": "aop__nombre", "tipo_documento": "tipo_documento__nombre", "tipo_ingreso": "tipo_ingreso__nombre",
         "tecnico": "tecnico", "legal": "legal", "categoria": "categoria__nombre", "fecha_resultado": "fecha_resultado",
         "fecha_recepcion": "fecha_recepcion", "representante": "aop__representante__nombre", "consultor": "aop__consultor__nombre"}
# Filtros que dependen de una columna: si el rol no la ve, tampoco puede filtrar por ella.
FILTRO_COLUMNA = {"tipo_documento": "tipo_documento", "categoria": "categoria", "tipo_ingreso": "tipo_ingreso",
                  "tecnico": "tecnico", "legal": "legal", "municipio": "municipios"}


# ---------------------------------------------------------------- columnas


def columnas_permitidas(usuario):
    if alcance.administra_licencias(usuario):
        return [c for c, _ in COLUMNAS]
    permitidas = set(ConfiguracionLicencias.actual().columnas_funcionario)
    return [c for c, _ in COLUMNAS if c in permitidas]


def columnas_visibles(usuario):
    permitidas = columnas_permitidas(usuario)
    elegidas = PreferenciaColumnas.objects.filter(usuario=usuario).values_list("columnas", flat=True).first()
    visibles = [c for c in permitidas if c in elegidas] if elegidas else permitidas
    return visibles or permitidas


def guardar_columnas(usuario, columnas):
    permitidas = columnas_permitidas(usuario)
    PreferenciaColumnas.objects.update_or_create(usuario=usuario, defaults={"columnas": [c for c in columnas if c in permitidas]})


# ---------------------------------------------------------------- consulta


def _entero(valor):
    valor = str(valor or "").strip()
    return int(valor) if valor.isdigit() else None


def _fecha(valor):
    try:
        return date.fromisoformat(str(valor))
    except ValueError:
        return None


def consulta(usuario, parametros):
    """(queryset, pestaña) con los filtros de la URL. Lo que el rol no ve no se puede filtrar."""
    pestana = parametros.get("pestana", "tramites")
    if pestana not in dict(PESTANAS) or (pestana == "papelera" and not alcance.administra_licencias(usuario)):
        pestana = "tramites"
    qs = Tramite.objects.select_related("aop__representante", "aop__consultor", "tipo_documento", "tipo_ingreso",
                                        "categoria", "proyecto", "registrado_por").prefetch_related("aop__municipios")
    if pestana == "papelera":
        qs = qs.filter(eliminado=True)
    else:
        qs = qs.filter(eliminado=False)
        consultas = Q(tipo_documento__es_consulta_categoria=True)
        qs = qs.filter(consultas) if pestana == "consultas" else qs.exclude(consultas)

    permitidas = set(columnas_permitidas(usuario))
    puede = lambda filtro: FILTRO_COLUMNA.get(filtro) in permitidas  # noqa: E731
    for filtro, campo in (("tipo_documento", "tipo_documento_id"), ("categoria", "categoria_id"),
                          ("tipo_ingreso", "tipo_ingreso_id"), ("municipio", "aop__municipios")):
        valor = _entero(parametros.get(filtro))
        if valor and puede(filtro):
            qs = qs.filter(**{campo: valor})
    for filtro in ("tecnico", "legal"):
        valor = str(parametros.get(filtro) or "").strip()
        if valor and puede(filtro):
            qs = qs.filter(**{f"{filtro}__icontains": valor})
    anio = _entero(parametros.get("anio"))
    if anio:
        qs = qs.filter(fecha_presentacion__year=anio)
    desde, hasta = _fecha(parametros.get("desde")), _fecha(parametros.get("hasta"))
    if desde:
        qs = qs.filter(fecha_presentacion__gte=desde)
    if hasta:
        qs = qs.filter(fecha_presentacion__lte=hasta)
    q = str(parametros.get("q") or "").strip()
    if q:
        busqueda = (Q(aop__nombre__icontains=q) | Q(numero__icontains=q) | Q(numero_asignado__icontains=q)
                    | Q(aop__representante__nombre__icontains=q) | Q(aop__consultor__nombre__icontains=q))
        if "observaciones" in permitidas:
            busqueda |= Q(observaciones__icontains=q)
        qs = qs.filter(busqueda)

    orden = parametros.get("orden", "")
    campo = ORDEN.get(orden.lstrip("-"))
    if campo and orden.lstrip("-") in permitidas:
        qs = qs.order_by(("-" if orden.startswith("-") else "") + campo, "-id")
    else:
        qs = qs.order_by("-fecha_presentacion", "-id")
    return qs.distinct(), pestana


# ---------------------------------------------------------------- celdas


class Contexto:
    """Datos que se calculan una vez por página (feriados, días de aviso, hoy)."""

    def __init__(self):
        self.feriados = set(Feriado.objects.values_list("fecha", flat=True))
        self.aviso = ConfiguracionLicencias.actual().dias_aviso
        self.hoy = date.today()

    def estado_vencimiento(self, tramite):
        """(fecha, "vencido" | "por_vencer" | "") — los trámites en categoría final no vencen."""
        fecha = vencimiento(tramite, self.feriados)
        if fecha is None or (tramite.categoria and tramite.categoria.es_final):
            return fecha, ""
        if fecha < self.hoy:
            return fecha, "vencido"
        if fecha <= self.hoy + timedelta(days=self.aviso):
            return fecha, "por_vencer"
        return fecha, ""


def _persona(p):
    return p.nombre if p else ""


def valor(tramite, clave, ctx):
    t = tramite
    if clave == "municipios":
        return ", ".join(m.nombre for m in t.aop.municipios.all())
    if clave == "mes":
        return t.fecha_presentacion.month if t.fecha_presentacion else None
    if clave == "anio":
        return t.fecha_presentacion.year if t.fecha_presentacion else None
    if clave == "aop":
        return t.aop.nombre
    if clave == "representante":
        return _persona(t.aop.representante)
    if clave == "consultor":
        return _persona(t.aop.consultor)
    if clave == "telefono":
        persona = t.aop.consultor or t.aop.representante
        return persona.telefono if persona else ""
    if clave == "entregado":
        return "Sí" if t.entregado else "No"
    if clave == "vencimiento":
        return ctx.estado_vencimiento(t)[0]
    if clave == "proyecto":
        return t.proyecto.codigo if t.proyecto else ""
    if clave == "registrado_por":
        return str(t.registrado_por or "")
    dato = getattr(t, clave)
    if clave in ("tipo_documento", "tipo_ingreso", "categoria"):
        return dato.nombre if dato else _original(t, clave)
    return dato


def _original(tramite, clave):
    """Si el valor no coincide con la configuración, se muestra el texto como se escribió (entre comillas)."""
    texto = (tramite.texto_original or {}).get(clave)
    return f"«{texto}»" if texto else ""


def filas(tramites, columnas, ctx):
    for t in tramites:
        _, estado = ctx.estado_vencimiento(t)
        yield t, estado, [valor(t, c, ctx) for c in columnas]
