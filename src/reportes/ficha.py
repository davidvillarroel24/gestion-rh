"""
Ficha técnica (Fase 10), con el formato de `Ficha tecnica/1FICHA TECNICA.xlsx`.

La ficha resume un GRUPO de proyectos (los filtros o la selección del visor): un
programa en una gestión, un municipio, o un solo proyecto. Se puede pedir una
ficha del conjunto o una por proyecto. Título y objetivo los escribe el usuario
al generarla (no se guardan).

Contenido: ubicación política (mapa + provincias/municipios), población
beneficiaria, acciones por tipo de proyecto (cantidad, materiales, indicadores,
municipios), objetivo y costo de inversión por tipo de fuente con montos en
letras. Los documentos no van en la ficha (D20).
"""

import json
from collections import defaultdict
from decimal import Decimal

from proyectos.models import Financiamiento, Geometria, Medicion, ProyectoMaterial

from .letras import bolivianos

CERO = Decimal("0")
MAXIMO_SEPARADAS = 60  # fichas por proyecto en una sola página
POBLACION = ("Familias beneficiadas", "Personas beneficiadas")
FUENTES = {  # tipo de fuente -> cómo se nombra en la ficha (orden de aparición)
    "Gobernación": "Gobierno Autónomo Departamental de Cochabamba",
    "Municipio": "Gobiernos Autónomos Municipales",
    "Externo": "Financiamiento externo",
}


def _valores_indicadores(ids):
    """{(proyecto, indicador): (valor, unidad, es_meta)}: último seguimiento; si no hay, la última meta. Sin desagregación."""
    ultimo = {}  # en orden de fecha: el último de cada momento pisa a los anteriores
    for m in (Medicion.objects.filter(proyecto_id__in=ids, desagregacion=None,
                                      momento__in=(Medicion.SEGUIMIENTO, Medicion.META))
              .select_related("indicador").order_by("fecha", "id")):
        ultimo[(m.proyecto_id, m.indicador.nombre, m.momento)] = m
    elegido = {}
    for momento in (Medicion.META, Medicion.SEGUIMIENTO):  # el seguimiento pisa a la meta
        for (proyecto_id, indicador, mom), m in ultimo.items():
            if mom == momento:
                elegido[(proyecto_id, indicador)] = (m.valor, m.indicador.unidad_medida, momento == Medicion.META)
    return elegido


def numero(valor, decimales=None):
    """Formato boliviano: 1.834.440,00. Sin decimales si el valor es entero (salvo que se pidan)."""
    valor = Decimal(valor)
    if decimales is None:
        decimales = 0 if valor == valor.to_integral_value() else 2
    return f"{valor:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _con_texto(filas):
    """Agrega 'texto' (ej. '4.501 bolsas', '18.046 m² (meta)') a cada suma."""
    return [{**f, "texto": f"{numero(f['valor'])} {f['unidad']}" + (" (meta)" if f["incluye_metas"] else ""),
             "beneficiarios": f"{numero(f['valor'])} {f['unidad'].capitalize()} Beneficiarias"} for f in filas]


def _suma(destino, nombre, valor, unidad, es_meta):
    fila = destino.setdefault(nombre, {"nombre": nombre, "valor": CERO, "unidad": unidad, "incluye_metas": False})
    fila["valor"] += valor
    fila["incluye_metas"] |= es_meta


def armar(proyectos, titulo="", objetivo="", modo="conjunto"):
    """Lista de fichas. proyectos: lista ya filtrada (con municipios, programa, tipo y estado precargados)."""
    ids = [p.pk for p in proyectos]
    indicadores = _valores_indicadores(ids)
    materiales = defaultdict(list)
    for pm in ProyectoMaterial.objects.filter(proyecto_id__in=ids).select_related("material"):
        materiales[pm.proyecto_id].append(pm)
    financiamientos = defaultdict(list)
    for f in Financiamiento.objects.filter(proyecto_id__in=ids).select_related("entidad__tipo_fuente"):
        financiamientos[f.proyecto_id].append(f)
    geometrias = defaultdict(list)
    for proyecto_id, geom in Geometria.objects.filter(proyecto_id__in=ids).values_list("proyecto_id", "geom"):
        geometrias[proyecto_id].append(geom)

    datos = {"indicadores": indicadores, "materiales": materiales, "financiamientos": financiamientos,
             "geometrias": geometrias}
    if modo == "separado":
        return [_ficha([p], titulo or p.nombre, objetivo, datos) for p in proyectos[:MAXIMO_SEPARADAS]]
    return [_ficha(proyectos, titulo or titulo_sugerido(proyectos), objetivo, datos)]


def titulo_sugerido(proyectos):
    if len(proyectos) == 1:
        return proyectos[0].nombre
    programas = {p.programa.nombre for p in proyectos if p.programa_id}
    gestiones = {p.gestion for p in proyectos if p.gestion}
    if len(programas) == 1:
        return programas.pop() + (f" – gestión {gestiones.pop()}" if len(gestiones) == 1 else "")
    return "Proyectos seleccionados"


def _ficha(proyectos, titulo, objetivo, datos):
    municipios = sorted({m.nombre for p in proyectos for m in p.municipios.all()})
    provincias = sorted({m.provincia.nombre for p in proyectos for m in p.municipios.all()})

    poblacion, acciones = {}, {}
    for p in proyectos:
        tipo = p.tipo.nombre if p.tipo_id else "Otros proyectos"
        accion = acciones.setdefault(tipo, {"tipo": tipo, "cantidad": 0, "materiales": {}, "indicadores": {},
                                            "municipios": set()})
        accion["cantidad"] += 1
        accion["municipios"].update(m.nombre for m in p.municipios.all())
        for pm in datos["materiales"][p.pk]:
            _suma(accion["materiales"], pm.material.nombre, pm.cantidad, pm.material.unidad_medida, False)
        for (proyecto_id, indicador), (valor, unidad, es_meta) in datos["indicadores"].items():
            if proyecto_id != p.pk:
                continue
            _suma(poblacion if indicador in POBLACION else accion["indicadores"], indicador, valor, unidad, es_meta)

    costos, total = {}, CERO
    for p in proyectos:
        for f in datos["financiamientos"][p.pk]:
            fuente = f.entidad.tipo_fuente.nombre
            fila = costos.setdefault(fuente, {"fuente": FUENTES.get(fuente, fuente), "monto": CERO, "entidades": set()})
            fila["monto"] += f.monto_comprometido
            fila["entidades"].add(f.entidad.nombre)
            total += f.monto_comprometido
    orden = list(FUENTES)
    filas_costo = []
    for fuente, fila in sorted(costos.items(), key=lambda x: orden.index(x[0]) if x[0] in orden else len(orden)):
        entidades = sorted(fila["entidades"])
        if fuente != "Gobernación" and len(entidades) == 1:
            fila["fuente"] = entidades[0]  # un solo GAM o un solo financiador: su nombre
        porcentaje = fila["monto"] * 100 / total if total else None
        filas_costo.append({**fila, "entidades": entidades, "monto_texto": numero(fila["monto"], 2),
                            "porcentaje": numero(porcentaje.quantize(Decimal("0.01"))) if porcentaje is not None else "",
                            "letras": bolivianos(fila["monto"])})

    rasgos = [{"type": "Feature", "properties": {}, "geometry": json.loads(g.json)}
              for p in proyectos for g in datos["geometrias"][p.pk]]
    unico = proyectos[0] if len(proyectos) == 1 else None
    return {
        "titulo": titulo,
        "objetivo": objetivo,
        "proyecto": unico,
        "cantidad_proyectos": len(proyectos),
        "provincias": provincias,
        "municipios": municipios,
        "poblacion": _con_texto(poblacion.values()),
        "acciones": [{**a, "materiales": _con_texto(a["materiales"].values()), "indicadores": _con_texto(a["indicadores"].values()),
                      "municipios": len(a["municipios"])} for a in acciones.values()],
        "costos": filas_costo,
        "total": total,
        "total_texto": numero(total, 2),
        "total_letras": bolivianos(total) if total else "",
        "geojson": {"type": "FeatureCollection", "features": rasgos},
    }
