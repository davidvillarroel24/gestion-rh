"""
Definición de las tablas importables/exportables (README de diseño §8.2–8.3).

Cada tabla declara UNA vez sus columnas; de ahí salen la plantilla Excel, la
importación y la exportación. Por eso un Excel exportado se puede corregir y
volver a importar tal cual.

En las planillas nunca se escriben IDs: los proyectos se identifican por su
código (RIE-2026-0001), los municipios por nombre o código INE y los catálogos
por su nombre (sin importar mayúsculas ni tildes).
"""

from dataclasses import dataclass, field

from django.contrib.gis.geos import GEOSException, GEOSGeometry, Point
from django.core.exceptions import ValidationError

from core import alcance
from core.models import Entidad, Persona, TipoDocumento, TipoEvento, TipoFuente
from core.texto import normalizar
from proyectos import consultas
from proyectos.models import (
    Avance, Desagregacion, Desembolso, DetalleForestacion, DetalleResiduos, EstadoProyecto, Evento, Financiamiento,
    Geometria, Indicador, Material, Medicion, Programa, Proposito, Proyecto, ProyectoMaterial, TipoElemento, TipoPlanta,
    TipoProyecto,
)
from territorio.models import Municipio

from . import valores as v
from .models import Cambio

SISTEMAS = [("4326", "WGS84 (latitud, longitud)"), ("32719", "UTM 19S (este, norte)"), ("32720", "UTM 20S (este, norte)")]

# Catálogos que se pueden crear al importar con solo el nombre (los demás piden más datos).
CREABLES = {EstadoProyecto, Programa, TipoProyecto, Desagregacion, TipoEvento, TipoDocumento, Proposito, TipoPlanta}


class ErrorFila(Exception):
    def __init__(self, mensajes):
        super().__init__("; ".join(mensajes))
        self.mensajes = mensajes


@dataclass
class Columna:
    titulo: str
    clave: str
    tipo: str = "texto"            # texto | entero | decimal | fecha | booleano | opcion | referencia
    obligatorio: bool = False
    ayuda: str = ""
    referencia: object = None      # "proyecto" | "unidad" | "municipio" | "entidad" | "tipo_fuente" | modelo de catálogo
    opciones: list = None          # [(valor_interno, etiqueta)]
    solo_exportar: bool = False    # calculadas: se exportan, la importación las ignora


@dataclass
class Tabla:
    clave: str
    titulo: str
    descripcion: str
    modelo: type
    columnas: list
    guardar: object = None         # (datos, contexto) -> "creado" | "actualizado" | "sin cambios"
    exportar: object = None        # (proyectos visibles filtrados, usuario) -> filas (listas de valores)
    de_proyectos: bool = True      # si sus filas cuelgan de proyectos (se filtran por alcance/filtros)
    ejemplo: list = field(default_factory=list)

    @property
    def columnas_importables(self):
        return [c for c in self.columnas if not c.solo_exportar]


class Contexto:
    """Estado de una importación: usuario, alcance, opciones y cambios hechos."""

    def __init__(self, usuario, crear_catalogos=False):
        self.usuario = usuario
        self.crear_catalogos = crear_catalogos
        self.proyectos = consultas.visibles(usuario)
        self.unidades = alcance.unidades_visibles(usuario)
        self.cambios = []
        self.sin_municipios = {}  # proyecto_id -> no tenía municipios al empezar la importación
        self._municipios = None

    def permiso(self, modelo, accion):
        codigo = f"{modelo._meta.app_label}.{accion}_{modelo._meta.model_name}"
        if not self.usuario.has_perm(codigo):
            raise ErrorFila([f"Su rol no permite {'crear' if accion == 'add' else 'modificar'} {modelo._meta.verbose_name_plural}."])

    def registrar(self, obj, accion, previa=None, extra=None):
        self.cambios.append({"objeto": obj, "accion": accion, "previa": previa, "importada": _ultima_version(obj)
                             if accion == Cambio.ACTUALIZADO else None, "extra": extra or {}})

    def municipio(self, texto):
        if self._municipios is None:
            self._municipios = {}
            for m in Municipio.objects.all():
                self._municipios[normalizar(m.nombre)] = m
                if m.codigo_ine:
                    self._municipios[m.codigo_ine] = m
        return self._municipios.get(texto.strip()) or self._municipios.get(normalizar(texto))


# ---------------------------------------------------------------- resolución de referencias


def _sugerencia(modelo, texto, **ambito):
    parecidos = modelo.parecidos(texto, **ambito) if hasattr(modelo, "parecidos") else []
    return f" ¿Quiso decir: {', '.join(p.nombre for p in parecidos)}?" if parecidos else ""


def resolver(columna, texto, datos, ctx):
    ref = columna.referencia
    clave = normalizar(texto)
    if ref == "proyecto":
        obj = ctx.proyectos.filter(codigo__iexact=texto.strip()).first()
        if obj is None:
            raise v.ErrorValor(f"no existe el proyecto «{texto}» o está fuera de su alcance.")
        return obj
    if ref == "unidad":
        obj = ctx.unidades.filter(clave=clave).first()
        if obj is None:
            raise v.ErrorValor(f"la unidad «{texto}» no existe o está fuera de su alcance.")
        return obj
    if ref == "municipio":
        obj = ctx.municipio(texto)
        if obj is None:
            raise v.ErrorValor(f"no existe el municipio «{texto}».")
        return obj
    if ref in ("entidad", "tipo_fuente"):
        modelo = Entidad if ref == "entidad" else TipoFuente
        obj = modelo.objects.filter(clave=clave).first()
        if obj is None:
            raise v.ErrorValor(f"no existe «{texto}».{_sugerencia(modelo, texto)}")
        return obj

    # Catálogo (global o por unidad)
    modelo = ref
    ambito = {}
    if modelo.campos_ambito:
        unidad = datos.get("unidad") or getattr(datos.get("proyecto"), "unidad", None)
        if unidad is None:
            raise v.ErrorValor("primero indique el proyecto o la unidad (columna obligatoria).")
        ambito = {"unidad": unidad}
    obj = modelo.objects.filter(clave=clave, **ambito).first()
    if obj:
        return obj
    puede_crear = (ctx.crear_catalogos and modelo in CREABLES
                   and ctx.usuario.has_perm(f"{modelo._meta.app_label}.add_{modelo._meta.model_name}"))
    if not puede_crear:
        raise v.ErrorValor(f"«{texto}» no está en {modelo._meta.verbose_name_plural}.{_sugerencia(modelo, texto, **ambito)}")
    obj = modelo(nombre=texto, **ambito)
    obj.full_clean()
    obj.save()
    ctx.registrar(obj, Cambio.CREADO)
    return obj


def convertir(columna, valor, datos, ctx):
    if columna.tipo == "referencia":
        return resolver(columna, v.texto(valor), datos, ctx)
    if columna.tipo == "opcion":
        return v.opcion(valor, columna.opciones)
    convertidor = {"texto": v.texto, "entero": v.entero, "decimal": v.decimal, "fecha": v.fecha, "booleano": v.booleano}
    return convertidor[columna.tipo](valor)


# ---------------------------------------------------------------- guardado


def _ultima_version(obj):
    historial = getattr(obj, "history", None)
    return historial.order_by("-history_id").values_list("history_id", flat=True).first() if historial else None


def _asignar(obj, campos):
    """Asigna y dice si algo cambió (para no registrar actualizaciones vacías)."""
    cambio = False
    for nombre, valor in campos.items():
        campo = obj._meta.get_field(nombre)
        if campo.is_relation:  # comparar por id: en un objeto nuevo la relación aún no existe
            actual, nuevo = getattr(obj, campo.attname), (valor.pk if valor is not None else None)
        else:
            actual, nuevo = getattr(obj, nombre), valor
        if actual != nuevo:
            setattr(obj, nombre, valor)
            cambio = True
    return cambio


def _guardar(obj, ctx, nuevo):
    try:
        obj.full_clean()
    except ValidationError as e:
        raise ErrorFila([f"{_etiqueta(obj, campo)}: {' '.join(m)}" if campo != "__all__" else " ".join(m)
                         for campo, m in e.message_dict.items()])
    previa = None if nuevo else _ultima_version(obj)
    obj.save()
    ctx.registrar(obj, Cambio.CREADO if nuevo else Cambio.ACTUALIZADO, previa=previa)
    return Cambio.CREADO if nuevo else Cambio.ACTUALIZADO


def _etiqueta(obj, campo):
    try:
        return str(obj._meta.get_field(campo).verbose_name).capitalize()
    except Exception:
        return campo


def _crear_o_actualizar(modelo, ctx, buscar, campos, nuevos=None):
    """Busca por la clave natural; actualiza si existe, crea si no."""
    obj = modelo.objects.filter(**buscar).first()
    nuevo = obj is None
    ctx.permiso(modelo, "add" if nuevo else "change")
    if nuevo:
        obj = modelo(**buscar, **(nuevos or {}))
    if not _asignar(obj, campos) and not nuevo:
        return "sin cambios"
    return _guardar(obj, ctx, nuevo)


def _vacio(valor):
    return "" if valor is None else valor


# ---- proyectos

def guardar_proyecto(d, ctx):
    obj = None
    if d.get("codigo"):
        obj = ctx.proyectos.filter(codigo__iexact=d["codigo"]).first()
        if obj is None:
            raise ErrorFila([f"Código: no existe «{d['codigo']}» (déjelo vacío para crear un proyecto nuevo)."])
    nuevo = obj is None
    ctx.permiso(Proyecto, "add" if nuevo else "change")
    if nuevo:
        obj = Proyecto(creado_por=ctx.usuario)
    campos = {
        "unidad": d["unidad"], "nombre": d["nombre"], "programa": d.get("programa"), "tipo": d.get("tipo"),
        "entidad_ejecutora": d.get("entidad_ejecutora"), "sisin": _vacio(d.get("sisin")),
        "comunidad": _vacio(d.get("comunidad")), "gestion": d.get("gestion"),
        "fecha_orden_proceder": d.get("fecha_orden_proceder"), "fecha_conclusion": d.get("fecha_conclusion"),
        "observaciones": _vacio(d.get("observaciones")),
    }
    if not _asignar(obj, campos) and not nuevo:
        return "sin cambios"
    return _guardar(obj, ctx, nuevo)


def exportar_proyectos(qs, usuario):
    qs = consultas.con_totales(qs).select_related("unidad", "programa", "tipo", "entidad_ejecutora", "estado")
    for p in qs.prefetch_related("municipios").order_by("codigo"):
        costo, pagado = p.total_comprometido, p.total_desembolsado
        yield [p.codigo, p.unidad.nombre, p.nombre, _n(p.programa), _n(p.tipo), _n(p.entidad_ejecutora), p.sisin,
               p.comunidad, p.gestion, p.fecha_orden_proceder, p.fecha_conclusion, p.observaciones,
               _n(p.estado), ", ".join(m.nombre for m in p.municipios.all()), costo, pagado,
               round(pagado * 100 / costo, 2) if costo else None, p.ultimo_avance_fisico]


def _n(obj):
    return obj.nombre if obj is not None else ""


# ---- municipios del proyecto (N:M)

def guardar_proyecto_municipio(d, ctx):
    ctx.permiso(Proyecto, "change")
    proyecto, municipio = d["proyecto"], d["municipio"]
    if proyecto.municipios.filter(pk=municipio.pk).exists():
        return "sin cambios"
    proyecto.municipios.add(municipio)
    ctx.registrar(proyecto, Cambio.RELACION, extra={"municipio": municipio.pk})
    return Cambio.RELACION


def exportar_proyecto_municipios(qs, usuario):
    for p in qs.prefetch_related("municipios").order_by("codigo"):
        for m in p.municipios.all():
            yield [p.codigo, m.nombre]


# ---- financiamiento y desembolsos

def guardar_financiamiento(d, ctx):
    return _crear_o_actualizar(Financiamiento, ctx, {"proyecto": d["proyecto"], "entidad": d["entidad"]},
                               {"monto_comprometido": d["monto_comprometido"]})


def exportar_financiamientos(qs, usuario):
    for f in Financiamiento.objects.filter(proyecto__in=qs).select_related("proyecto", "entidad").order_by("proyecto__codigo", "id"):
        yield [f.proyecto.codigo, f.entidad.nombre, f.monto_comprometido, f.desembolsado]


def guardar_desembolso(d, ctx):
    financiamiento = Financiamiento.objects.filter(proyecto=d["proyecto"], entidad=d["entidad"]).first()
    if financiamiento is None:
        raise ErrorFila([f"El proyecto {d['proyecto'].codigo} no tiene financiamiento de «{d['entidad']}». "
                         "Cárguelo primero (tabla Financiamientos)."])
    comprobante = _vacio(d.get("comprobante"))
    if financiamiento.desembolsos.filter(fecha=d["fecha"], monto=d["monto"], comprobante=comprobante).exists():
        return "sin cambios"
    ctx.permiso(Desembolso, "add")
    obj = Desembolso(financiamiento=financiamiento, fecha=d["fecha"], monto=d["monto"], comprobante=comprobante,
                     descripcion=_vacio(d.get("descripcion")), excede_confirmado=bool(d.get("excede_confirmado")),
                     registrado_por=ctx.usuario)
    return _guardar(obj, ctx, True)


def exportar_desembolsos(qs, usuario):
    for x in Desembolso.objects.filter(financiamiento__proyecto__in=qs).select_related(
            "financiamiento__proyecto", "financiamiento__entidad").order_by("financiamiento__proyecto__codigo", "fecha"):
        yield [x.financiamiento.proyecto.codigo, x.financiamiento.entidad.nombre, x.fecha, x.monto, x.comprobante,
               x.descripcion, "Sí" if x.excede_confirmado else "No"]


# ---- avances, materiales, mediciones, bitácora

def guardar_avance(d, ctx):
    return _crear_o_actualizar(Avance, ctx, {"proyecto": d["proyecto"], "fecha": d["fecha"]},
                               {"fisico_pct": d["fisico_pct"], "observacion": _vacio(d.get("observacion"))})


def exportar_avances(qs, usuario):
    for a in Avance.objects.filter(proyecto__in=qs).select_related("proyecto").order_by("proyecto__codigo", "fecha"):
        yield [a.proyecto.codigo, a.fecha, a.fisico_pct, a.observacion]


def guardar_material(d, ctx):
    return _crear_o_actualizar(ProyectoMaterial, ctx, {"proyecto": d["proyecto"], "material": d["material"]},
                               {"cantidad": d["cantidad"]})


def exportar_materiales(qs, usuario):
    for m in ProyectoMaterial.objects.filter(proyecto__in=qs).select_related("proyecto", "material").order_by("proyecto__codigo"):
        yield [m.proyecto.codigo, m.material.nombre, m.cantidad]


def guardar_medicion(d, ctx):
    buscar = {"proyecto": d["proyecto"], "indicador": d["indicador"], "desagregacion": d.get("desagregacion"),
              "momento": d["momento"], "fecha": d["fecha"]}
    return _crear_o_actualizar(Medicion, ctx, buscar, {"valor": d["valor"], "fuente": _vacio(d.get("fuente"))},
                               nuevos={"registrado_por": ctx.usuario})


def exportar_mediciones(qs, usuario):
    for m in Medicion.objects.filter(proyecto__in=qs).select_related("proyecto", "indicador", "desagregacion").order_by("proyecto__codigo", "fecha"):
        yield [m.proyecto.codigo, m.indicador.nombre, _n(m.desagregacion), m.get_momento_display(), m.fecha, m.valor, m.fuente]


def guardar_evento(d, ctx):
    buscar = {"proyecto": d["proyecto"], "fecha": d["fecha"], "tipo": d["tipo"], "descripcion": d["descripcion"]}
    if Evento.objects.filter(**buscar).exists():
        return "sin cambios"
    ctx.permiso(Evento, "add")
    return _guardar(Evento(**buscar, estado_nuevo=d.get("estado_nuevo"), usuario=ctx.usuario), ctx, True)


def exportar_eventos(qs, usuario):
    for e in Evento.objects.filter(proyecto__in=qs).select_related("proyecto", "tipo", "estado_nuevo").order_by("proyecto__codigo", "fecha", "id"):
        yield [e.proyecto.codigo, e.fecha, e.tipo.nombre, e.descripcion, _n(e.estado_nuevo)]


# ---- geometrías (puntos por coordenadas o cualquier forma en WKT)

def guardar_geometria(d, ctx):
    ctx.permiso(Geometria, "add")
    if d.get("wkt"):
        try:
            geom = GEOSGeometry(d["wkt"], srid=4326)
        except (GEOSException, ValueError):
            raise ErrorFila(["WKT: no es una geometría válida."])
    elif d.get("x") is not None and d.get("y") is not None:
        srid = int(d.get("sistema") or 4326)
        geom = Point(float(d["y"]), float(d["x"]), srid=4326) if srid == 4326 else Point(float(d["x"]), float(d["y"]), srid=srid)
        if srid != 4326:
            geom.transform(4326)
    else:
        raise ErrorFila(["Indique las coordenadas (columnas 1 y 2) o la geometría en WKT."])
    proyecto = d["proyecto"]
    if Geometria.objects.filter(proyecto=proyecto, tipo_elemento=d["tipo_elemento"], geom__equals=geom).exists():
        return "sin cambios"
    obj = Geometria(proyecto=proyecto, tipo_elemento=d["tipo_elemento"], nombre=_vacio(d.get("nombre")), geom=geom)
    resultado = _guardar(obj, ctx, True)
    # Si el proyecto no tenía municipios al empezar la importación, se completan
    # con los que tocan TODAS sus geometrías importadas (no solo la primera).
    if proyecto.pk not in ctx.sin_municipios:
        ctx.sin_municipios[proyecto.pk] = not proyecto.municipios.exists()
    if ctx.sin_municipios[proyecto.pk]:
        for municipio in obj.municipios_que_toca().exclude(pk__in=proyecto.municipios.all()):
            proyecto.municipios.add(municipio)
            ctx.registrar(proyecto, Cambio.RELACION, extra={"municipio": municipio.pk})
    return resultado


def exportar_geometrias(qs, usuario):
    for g in Geometria.objects.filter(proyecto__in=qs).select_related("proyecto", "tipo_elemento").order_by("proyecto__codigo", "id"):
        es_punto = g.geom.geom_type == "Point"
        yield [g.proyecto.codigo, g.tipo_elemento.nombre, g.nombre, "WGS84 (latitud, longitud)" if es_punto else "",
               round(g.geom.y, 7) if es_punto else None, round(g.geom.x, 7) if es_punto else None, g.geom.wkt]


# ---- entidades, personas y catálogos (no cuelgan de proyectos)

# ---- detalle propio de cada unidad (1:1 con el proyecto)

def guardar_detalle_residuos(d, ctx):
    return _crear_o_actualizar(DetalleResiduos, ctx, {"proyecto": d["proyecto"]}, {
        "botadero": _vacio(d.get("botadero")), "licencia": _vacio(d.get("licencia")), "riesgo": _vacio(d.get("riesgo")),
        "ton_urbano": d.get("ton_urbano"), "ton_rural": d.get("ton_rural")})


def exportar_detalle_residuos(qs, usuario):
    for x in DetalleResiduos.objects.filter(proyecto__in=qs).select_related("proyecto").order_by("proyecto__codigo"):
        yield [x.proyecto.codigo, x.botadero, x.licencia, x.riesgo, x.ton_urbano, x.ton_rural, x.ton_total]


def guardar_detalle_forestacion(d, ctx):
    return _crear_o_actualizar(DetalleForestacion, ctx, {"proyecto": d["proyecto"]}, {
        "proposito": d.get("proposito"), "campania": _vacio(d.get("campania")), "plantines": d.get("plantines"),
        "tipo_planta": d.get("tipo_planta")})


def exportar_detalle_forestacion(qs, usuario):
    for x in DetalleForestacion.objects.filter(proyecto__in=qs).select_related("proyecto", "proposito", "tipo_planta").order_by("proyecto__codigo"):
        yield [x.proyecto.codigo, _n(x.proposito), x.campania, x.plantines, _n(x.tipo_planta)]


def guardar_entidad(d, ctx):
    return _crear_o_actualizar(Entidad, ctx, {"clave": normalizar(d["nombre"])},
                               {"nombre": d["nombre"], "tipo_fuente": d["tipo_fuente"], "municipio": d.get("municipio")})


def exportar_entidades(qs, usuario):
    for e in Entidad.objects.select_related("tipo_fuente", "municipio").order_by("nombre"):
        yield [e.nombre, e.tipo_fuente.nombre, _n(e.municipio)]


def guardar_persona(d, ctx):
    buscar = {"ci": d["ci"]} if d.get("ci") else {"nombre": d["nombre"], "ci": None}
    return _crear_o_actualizar(Persona, ctx, buscar, {"nombre": d["nombre"], "telefono": _vacio(d.get("telefono")),
                                                       "correo": _vacio(d.get("correo"))})


def exportar_personas(qs, usuario):
    for p in Persona.objects.order_by("nombre"):
        yield [p.nombre, p.ci or "", p.telefono, p.correo]


def tabla_catalogo(clave, modelo, extras=()):
    """Tabla genérica de un catálogo: Nombre (+ Unidad si es por unidad) + columnas propias."""
    por_unidad = bool(modelo.campos_ambito)
    columnas = ([Columna("Unidad", "unidad", "referencia", True, referencia="unidad")] if por_unidad else [])
    columnas += [Columna("Nombre", "nombre", obligatorio=True)] + list(extras)

    def guardar(d, ctx):
        buscar = {"clave": normalizar(d["nombre"])}
        if por_unidad:
            buscar["unidad"] = d["unidad"]
        campos = {"nombre": d["nombre"], **{c.clave: d.get(c.clave) for c in extras if d.get(c.clave) is not None}}
        return _crear_o_actualizar(modelo, ctx, buscar, campos)

    def exportar(qs, usuario):
        objetos = modelo.objects.all()
        if por_unidad:
            objetos = objetos.filter(unidad__in=alcance.unidades_visibles(usuario)).select_related("unidad")
        for o in objetos.order_by(*(["unidad__nombre"] if por_unidad else []), "nombre"):
            fila = ([o.unidad.nombre] if por_unidad else []) + [o.nombre]
            for c in extras:
                valor = getattr(o, c.clave)
                fila.append(dict(c.opciones).get(valor, valor) if c.opciones else valor)
            yield fila

    return Tabla(clave, str(modelo._meta.verbose_name_plural).capitalize(),
                 f"Catálogo de {modelo._meta.verbose_name_plural}.", modelo, columnas, guardar, exportar, de_proyectos=False)


# ---------------------------------------------------------------- registro de tablas

COL_PROYECTO = Columna("Código de proyecto", "proyecto", "referencia", True, "Código del sistema, ej. RIE-2026-0001.", referencia="proyecto")

TABLAS = {t.clave: t for t in [
    Tabla("proyectos", "Proyectos", "Datos generales. Código vacío = proyecto nuevo; con código = actualiza ese proyecto.", Proyecto, [
        Columna("Código", "codigo", ayuda="Vacío para crear un proyecto nuevo (el sistema asigna el código)."),
        Columna("Unidad", "unidad", "referencia", True, referencia="unidad"),
        Columna("Nombre", "nombre", obligatorio=True),
        Columna("Programa", "programa", "referencia", referencia=Programa),
        Columna("Tipo de proyecto", "tipo", "referencia", referencia=TipoProyecto),
        Columna("Entidad ejecutora", "entidad_ejecutora", "referencia", referencia="entidad"),
        Columna("SISIN", "sisin"),
        Columna("Comunidad", "comunidad"),
        Columna("Gestión", "gestion", "entero"),
        Columna("Orden de proceder", "fecha_orden_proceder", "fecha"),
        Columna("Fecha de conclusión", "fecha_conclusion", "fecha"),
        Columna("Observaciones", "observaciones"),
        Columna("Estado", "estado", solo_exportar=True, ayuda="Lo fija la bitácora."),
        Columna("Municipios", "municipios", solo_exportar=True, ayuda="Se cargan en la tabla Municipios de proyectos."),
        Columna("Costo total (Bs)", "costo_total", "decimal", solo_exportar=True),
        Columna("Desembolsado (Bs)", "desembolsado", "decimal", solo_exportar=True),
        Columna("Avance financiero (%)", "avance_financiero", "decimal", solo_exportar=True),
        Columna("Avance físico (%)", "avance_fisico", "decimal", solo_exportar=True),
    ], guardar_proyecto, exportar_proyectos,
        ejemplo=["", "Riego", "Sistema de riego Ejemplo", "Mi Riego", "Proyecto menor", "FPS", "", "Comunidad X", 2026, "15/03/2026", "15/12/2026", ""]),
    Tabla("proyecto_municipios", "Municipios de proyectos", "Un renglón por cada municipio que abarca un proyecto.", Proyecto, [
        COL_PROYECTO, Columna("Municipio", "municipio", "referencia", True, "Nombre o código INE.", referencia="municipio"),
    ], guardar_proyecto_municipio, exportar_proyecto_municipios, ejemplo=["RIE-2026-0001", "Punata"]),
    Tabla("financiamientos", "Financiamientos", "Monto comprometido por cada entidad (Gobernación, GAM, externo).", Financiamiento, [
        COL_PROYECTO, Columna("Entidad", "entidad", "referencia", True, referencia="entidad"),
        Columna("Monto comprometido (Bs)", "monto_comprometido", "decimal", True),
        Columna("Desembolsado (Bs)", "desembolsado", "decimal", solo_exportar=True),
    ], guardar_financiamiento, exportar_financiamientos, ejemplo=["RIE-2026-0001", "GAM Punata", "150000"]),
    Tabla("desembolsos", "Desembolsos", "Pagos contra el compromiso de una entidad (el financiamiento debe existir).", Desembolso, [
        COL_PROYECTO, Columna("Entidad", "entidad", "referencia", True, referencia="entidad"),
        Columna("Fecha", "fecha", "fecha", True), Columna("Monto (Bs)", "monto", "decimal", True),
        Columna("Comprobante", "comprobante"), Columna("Descripción", "descripcion"),
        Columna("Excede lo comprometido (Sí/No)", "excede_confirmado", "booleano",
                ayuda="Sí solo si este pago supera a propósito lo comprometido."),
    ], guardar_desembolso, exportar_desembolsos, ejemplo=["RIE-2026-0001", "GAM Punata", "10/04/2026", "50000", "C-123", "Primer pago", "No"]),
    Tabla("avances", "Avances físicos", "Avance físico en una fecha (el financiero se calcula con los desembolsos).", Avance, [
        COL_PROYECTO, Columna("Fecha", "fecha", "fecha", True), Columna("Avance físico (%)", "fisico_pct", "decimal", True),
        Columna("Observación", "observacion"),
    ], guardar_avance, exportar_avances, ejemplo=["RIE-2026-0001", "30/06/2026", "45", ""]),
    Tabla("materiales", "Materiales", "Cantidad de cada material por proyecto.", ProyectoMaterial, [
        COL_PROYECTO, Columna("Material", "material", "referencia", True, referencia=Material),
        Columna("Cantidad", "cantidad", "decimal", True),
    ], guardar_material, exportar_materiales, ejemplo=["RIE-2026-0001", "Cemento", "120"]),
    Tabla("mediciones", "Mediciones", "Indicadores: línea base (antes), meta o seguimiento (después).", Medicion, [
        COL_PROYECTO, Columna("Indicador", "indicador", "referencia", True, referencia=Indicador),
        Columna("Desagregación", "desagregacion", "referencia", referencia=Desagregacion, ayuda="Ej. Hombres / Mujeres (opcional)."),
        Columna("Momento", "momento", "opcion", True, opciones=[(a, b.split(" (")[0]) for a, b in Medicion.MOMENTOS]),
        Columna("Fecha", "fecha", "fecha", True), Columna("Valor", "valor", "decimal", True), Columna("Fuente", "fuente"),
    ], guardar_medicion, exportar_mediciones, ejemplo=["RIE-2026-0001", "Familias beneficiadas", "", "Seguimiento", "01/10/2026", "45", "Encuesta"]),
    Tabla("eventos", "Bitácora", "Eventos del proyecto; si indica un estado nuevo, cambia el estado del proyecto.", Evento, [
        COL_PROYECTO, Columna("Fecha", "fecha", "fecha", True),
        Columna("Tipo de evento", "tipo", "referencia", True, referencia=TipoEvento),
        Columna("Descripción", "descripcion", obligatorio=True),
        Columna("Estado nuevo", "estado_nuevo", "referencia", referencia=EstadoProyecto),
    ], guardar_evento, exportar_eventos, ejemplo=["RIE-2026-0001", "01/04/2026", "Cambio de estado", "Inicio de obra", "En ejecución"]),
    Tabla("geometrias", "Geometrías", "Puntos por coordenadas, o cualquier forma en WKT (WGS84).", Geometria, [
        COL_PROYECTO, Columna("Tipo de elemento", "tipo_elemento", "referencia", True, referencia=TipoElemento),
        Columna("Nombre", "nombre"),
        Columna("Sistema de coordenadas", "sistema", "opcion", opciones=SISTEMAS, ayuda="Por defecto WGS84."),
        Columna("Coordenada 1 (latitud o este)", "x", "decimal"),
        Columna("Coordenada 2 (longitud o norte)", "y", "decimal"),
        Columna("Geometría WKT", "wkt", ayuda="Opcional: ej. LINESTRING(-65.8 -17.5, -65.79 -17.51). Si se llena, se ignoran las coordenadas."),
    ], guardar_geometria, exportar_geometrias, ejemplo=["RIE-2026-0001", "Toma de agua", "Toma principal", "WGS84 (latitud, longitud)", "-17.5221", "-65.7974", ""]),
    Tabla("detalle_residuos", "Detalle de residuos sólidos", "Datos propios de cada botadero (un renglón por proyecto).", DetalleResiduos, [
        COL_PROYECTO, Columna("Botadero", "botadero"), Columna("Licencia", "licencia"), Columna("Riesgo", "riesgo"),
        Columna("Toneladas urbano", "ton_urbano", "decimal"), Columna("Toneladas rural", "ton_rural", "decimal"),
        Columna("Toneladas total", "ton_total", "decimal", solo_exportar=True),
    ], guardar_detalle_residuos, exportar_detalle_residuos,
        ejemplo=["RES-2026-0001", "Botadero Municipal X", "Sin Licencia", "RIESGO MEDIO", "0", "8,28"]),
    Tabla("detalle_forestacion", "Detalle de forestación", "Datos propios de cada proyecto forestal (un renglón por proyecto).", DetalleForestacion, [
        COL_PROYECTO, Columna("Propósito", "proposito", "referencia", referencia=Proposito),
        Columna("Campaña", "campania"), Columna("Plantines", "plantines", "entero"),
        Columna("Tipo de planta", "tipo_planta", "referencia", referencia=TipoPlanta, ayuda="Solo si es una única especie."),
    ], guardar_detalle_forestacion, exportar_detalle_forestacion,
        ejemplo=["FOR-2026-0001", "Comercial", "2025-2026", "25800", ""]),
    Tabla("entidades", "Entidades", "Financiadores y ejecutores: Gobernación, gobiernos municipales, externos.", Entidad, [
        Columna("Nombre", "nombre", obligatorio=True),
        Columna("Tipo de fuente", "tipo_fuente", "referencia", True, referencia="tipo_fuente"),
        Columna("Municipio", "municipio", "referencia", referencia="municipio", ayuda="Solo para gobiernos municipales."),
    ], guardar_entidad, exportar_entidades, de_proyectos=False, ejemplo=["Cooperación Ejemplo", "Externo", ""]),
    Tabla("personas", "Personas", "Representantes, consultores, contactos. Se identifican por CI si lo tienen.", Persona, [
        Columna("Nombre", "nombre", obligatorio=True), Columna("CI", "ci"), Columna("Teléfono", "telefono"), Columna("Correo", "correo"),
    ], guardar_persona, exportar_personas, de_proyectos=False, ejemplo=["Juan Pérez", "1234567", "70000000", ""]),
    tabla_catalogo("estados", EstadoProyecto, [Columna("Orden", "orden", "entero")]),
    tabla_catalogo("programas", Programa),
    tabla_catalogo("tipos_proyecto", TipoProyecto),
    tabla_catalogo("tipos_elemento", TipoElemento, [Columna("Tipo de geometría", "tipo_geometria", "opcion", True, opciones=TipoElemento.TIPOS_GEOMETRIA)]),
    tabla_catalogo("indicadores", Indicador, [Columna("Unidad de medida", "unidad_medida", obligatorio=True),
                                              Columna("Categoría", "categoria", "opcion", opciones=Indicador.CATEGORIAS)]),
    tabla_catalogo("desagregaciones", Desagregacion),
    tabla_catalogo("materiales_catalogo", Material, [Columna("Unidad de medida", "unidad_medida", obligatorio=True)]),
    tabla_catalogo("tipos_evento", TipoEvento),
    tabla_catalogo("tipos_documento", TipoDocumento),
    tabla_catalogo("propositos", Proposito),
    tabla_catalogo("tipos_planta", TipoPlanta),
]}

# Tablas que van en "Exportar todo" (las que cuelgan de proyectos).
TABLAS_DE_PROYECTOS = [t for t in TABLAS.values() if t.de_proyectos]
