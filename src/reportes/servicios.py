"""
Cálculos de la Fase 8: tarjetas, agrupaciones, curva S, indicadores y alertas.

Regla del dinero (D10): el monto de un proyecto se cuenta UNA vez en el total.
- Agrupar por unidad, estado, programa, tipo o gestión: cada proyecto cae en un
  solo grupo, así que los grupos suman el total.
- Agrupar por municipio, provincia o región: un proyecto que abarca varios
  aparece en cada uno; los grupos pueden sumar más que el total, y el total
  general se calcula sobre proyectos distintos (se avisa en el reporte).
- Agrupar por fuente o entidad: se suman los compromisos, cada uno una vez.
"""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings

from proyectos import consultas
from proyectos.models import Avance, Desembolso, Financiamiento, Medicion

CERO = Decimal("0")

ALERTAS = {"dias_sin_avance": 90, "brecha_financiero_fisico": 25, **getattr(settings, "ALERTAS", {})}


def proyectos(usuario, parametros):
    qs = consultas.filtrar(consultas.visibles(usuario), parametros)
    return list(consultas.con_totales(qs).select_related("unidad", "estado", "programa", "tipo")
                .prefetch_related("municipios__provincia", "municipios__region").order_by("codigo"))


def _pct(parte, total):
    return round(float(parte) * 100 / float(total), 1) if total else None


# ---------------------------------------------------------------- tarjetas


def resumen(lista):
    comprometido = sum((p.total_comprometido for p in lista), CERO)
    desembolsado = sum((p.total_desembolsado for p in lista), CERO)
    fisicos = [(p.ultimo_avance_fisico, p.total_comprometido) for p in lista if p.ultimo_avance_fisico is not None]
    peso = sum((c for _, c in fisicos), CERO)
    fisico = (sum(f * c for f, c in fisicos) / peso if peso else
              (sum(f for f, _ in fisicos) / len(fisicos) if fisicos else None))
    municipios = {m.pk for p in lista for m in p.municipios.all()}
    return {
        "proyectos": len(lista),
        "comprometido": float(comprometido),
        "desembolsado": float(desembolsado),
        "saldo": float(comprometido - desembolsado),
        "avance_financiero": _pct(desembolsado, comprometido),
        "avance_fisico": round(float(fisico), 1) if fisico is not None else None,
        "municipios": len(municipios),
        "concluidos": sum(1 for p in lista if p.estado_id and p.estado.es_final),
    }


# ---------------------------------------------------------------- agrupaciones


def _nombre(obj, vacio):
    return obj.nombre if obj is not None else vacio


DIMENSIONES = {
    # clave: (título, función proyecto -> grupos, puede repetir proyectos entre grupos)
    "municipio": ("Municipio", lambda p: [m.nombre for m in p.municipios.all()] or ["Sin municipio"], True),
    "provincia": ("Provincia", lambda p: sorted({m.provincia.nombre for m in p.municipios.all()}) or ["Sin municipio"], True),
    "region": ("Región", lambda p: sorted({m.region.nombre for m in p.municipios.all()}) or ["Sin municipio"], True),
    "unidad": ("Unidad", lambda p: [p.unidad.nombre], False),
    "estado": ("Estado", lambda p: [_nombre(p.estado, "Sin estado")], False),
    "programa": ("Programa", lambda p: [_nombre(p.programa, "Sin programa")], False),
    "tipo": ("Tipo de proyecto", lambda p: [_nombre(p.tipo, "Sin tipo")], False),
    "gestion": ("Gestión", lambda p: [str(p.gestion) if p.gestion else "Sin gestión"], False),
    "fuente": ("Fuente de financiamiento", None, False),
    "entidad": ("Entidad financiadora", None, False),
}

MEDIDAS = {
    "proyectos": "Cantidad de proyectos",
    "comprometido": "Monto comprometido (Bs)",
    "desembolsado": "Monto desembolsado (Bs)",
    "avance_financiero": "Avance financiero (%)",
}


def _fila(grupo, proyectos_ids, comprometido, desembolsado):
    return {"grupo": grupo, "proyectos": len(proyectos_ids), "comprometido": float(comprometido),
            "desembolsado": float(desembolsado), "avance_financiero": _pct(desembolsado, comprometido)}


def agrupar(lista, por):
    titulo, grupos_de, repite = DIMENSIONES[por]
    if grupos_de is None:
        filas = _agrupar_financiamiento(lista, por)
    else:
        acumulado = defaultdict(lambda: {"ids": set(), "comprometido": CERO, "desembolsado": CERO})
        for p in lista:
            for grupo in grupos_de(p):
                g = acumulado[grupo]
                g["ids"].add(p.pk)
                g["comprometido"] += p.total_comprometido
                g["desembolsado"] += p.total_desembolsado
        filas = [_fila(k, v["ids"], v["comprometido"], v["desembolsado"]) for k, v in acumulado.items()]
        if por == "municipio":
            aportes = _aportes_municipales(lista)
            for f in filas:
                f["aporte_municipal"] = float(aportes.get(f["grupo"], CERO))

    total = resumen(lista)
    nota = None
    if repite:
        nota = (f"Un proyecto que abarca varios {titulo.lower()}s aparece en cada uno: las filas pueden sumar más que "
                "el total. El total general cuenta cada proyecto una sola vez.")
    elif por in ("fuente", "entidad"):
        nota = "Un proyecto con varias fuentes cuenta en cada una; los montos no se repiten."
    filas.sort(key=lambda f: (-f["comprometido"], -f["proyectos"], f["grupo"]))
    return {"por": por, "dimension": titulo, "filas": filas, "nota": nota,
            "total": {"proyectos": total["proyectos"], "comprometido": total["comprometido"],
                      "desembolsado": total["desembolsado"], "avance_financiero": total["avance_financiero"]}}


def _agrupar_financiamiento(lista, por):
    ids = [p.pk for p in lista]
    clave = "entidad__tipo_fuente__nombre" if por == "fuente" else "entidad__nombre"
    acumulado = defaultdict(lambda: {"ids": set(), "comprometido": CERO, "desembolsado": CERO})
    for proyecto_id, grupo, monto in Financiamiento.objects.filter(proyecto_id__in=ids).values_list("proyecto_id", clave, "monto_comprometido"):
        acumulado[grupo]["ids"].add(proyecto_id)
        acumulado[grupo]["comprometido"] += monto
    clave_desembolso = f"financiamiento__{clave}"
    for grupo, monto in Desembolso.objects.filter(financiamiento__proyecto_id__in=ids).values_list(clave_desembolso, "monto"):
        acumulado[grupo]["desembolsado"] += monto
    return [_fila(k, v["ids"], v["comprometido"], v["desembolsado"]) for k, v in acumulado.items()]


def _aportes_municipales(lista):
    """Contraparte de cada municipio = lo que comprometió su gobierno municipal (entidad con ese municipio)."""
    aportes = defaultdict(lambda: CERO)
    filas = Financiamiento.objects.filter(proyecto_id__in=[p.pk for p in lista], entidad__municipio__isnull=False)
    for nombre, monto in filas.values_list("entidad__municipio__nombre", "monto_comprometido"):
        aportes[nombre] += monto
    return aportes


# ---------------------------------------------------------------- curva S


def _fin_de_mes(d):
    siguiente = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return siguiente - timedelta(days=1)


def curva_s(lista, hoy=None, maximo_meses=120):
    """Avance físico (ponderado por monto comprometido) y financiero acumulado, mes a mes."""
    hoy = hoy or date.today()
    ids = [p.pk for p in lista]
    pagos = sorted(Desembolso.objects.filter(financiamiento__proyecto_id__in=ids).values_list("fecha", "monto"))
    avances = defaultdict(list)
    for proyecto_id, fecha, pct in Avance.objects.filter(proyecto_id__in=ids).order_by("fecha").values_list("proyecto_id", "fecha", "fisico_pct"):
        avances[proyecto_id].append((fecha, pct))
    fechas = [f for f, _ in pagos] + [f for serie in avances.values() for f, _ in serie]
    fechas += [p.fecha_orden_proceder for p in lista if p.fecha_orden_proceder]
    if not fechas:
        return {"meses": [], "fisico": [], "financiero": []}

    total = sum((p.total_comprometido for p in lista), CERO)
    pesos = {p.pk: (p.total_comprometido if total else Decimal(1)) for p in lista}
    peso_total = sum(pesos.values(), CERO) or Decimal(1)

    meses, fisico, financiero = [], [], []
    mes = _fin_de_mes(min(fechas))
    limite = _fin_de_mes(max(max(fechas), hoy))
    pagado, i = CERO, 0
    while mes <= limite:
        while i < len(pagos) and pagos[i][0] <= mes:
            pagado += pagos[i][1]
            i += 1
        ponderado = CERO
        for p in lista:
            ultimo = next((pct for f, pct in reversed(avances.get(p.pk, [])) if f <= mes), CERO)
            ponderado += ultimo * pesos[p.pk]
        meses.append(mes.strftime("%Y-%m"))
        fisico.append(round(float(ponderado / peso_total), 1))
        financiero.append(_pct(pagado, total))
        mes = _fin_de_mes(mes + timedelta(days=1))
    # Períodos muy largos: se muestran los meses más recientes.
    return {"meses": meses[-maximo_meses:], "fisico": fisico[-maximo_meses:], "financiero": financiero[-maximo_meses:]}


# ---------------------------------------------------------------- indicadores (antes / después)


def indicadores(lista):
    """Por indicador (y desagregación): suma entre proyectos del último valor de línea base, meta y seguimiento."""
    ultimos = {}
    filas = (Medicion.objects.filter(proyecto_id__in=[p.pk for p in lista])
             .select_related("indicador", "desagregacion").order_by("fecha", "id"))
    for m in filas:  # en orden de fecha: el último pisa a los anteriores
        ultimos[(m.indicador_id, m.desagregacion_id, m.proyecto_id, m.momento)] = m
    acumulado = {}
    for (indicador_id, desagregacion_id, _, momento), m in ultimos.items():
        clave = (indicador_id, desagregacion_id)
        fila = acumulado.setdefault(clave, {
            "indicador": m.indicador.nombre, "unidad_medida": m.indicador.unidad_medida,
            "desagregacion": m.desagregacion.nombre if m.desagregacion_id else "", "proyectos": set(),
            Medicion.LINEA_BASE: None, Medicion.META: None, Medicion.SEGUIMIENTO: None})
        fila["proyectos"].add(m.proyecto_id)
        fila[momento] = (fila[momento] or CERO) + m.valor
    resultado = []
    for fila in acumulado.values():
        base, seguimiento = fila[Medicion.LINEA_BASE], fila[Medicion.SEGUIMIENTO]
        resultado.append({
            "indicador": fila["indicador"], "unidad_medida": fila["unidad_medida"], "desagregacion": fila["desagregacion"],
            "proyectos": len(fila["proyectos"]),
            "linea_base": float(base) if base is not None else None,
            "meta": float(fila[Medicion.META]) if fila[Medicion.META] is not None else None,
            "seguimiento": float(seguimiento) if seguimiento is not None else None,
            "cambio": float(seguimiento - base) if base is not None and seguimiento is not None else None,
        })
    return sorted(resultado, key=lambda f: (f["indicador"], f["desagregacion"]))


# ---------------------------------------------------------------- alertas


def alertas(lista, hoy=None):
    hoy = hoy or date.today()
    dias, brecha = ALERTAS["dias_sin_avance"], ALERTAS["brecha_financiero_fisico"]
    ultimo_avance = {}
    for proyecto_id, fecha in Avance.objects.filter(proyecto_id__in=[p.pk for p in lista]).values_list("proyecto_id", "fecha"):
        ultimo_avance[proyecto_id] = max(fecha, ultimo_avance.get(proyecto_id, fecha))
    con_seguimiento = set(Medicion.objects.filter(proyecto_id__in=[p.pk for p in lista], momento=Medicion.SEGUIMIENTO)
                          .values_list("proyecto_id", flat=True))
    resultado = []

    def agregar(p, tipo, nivel, detalle):
        resultado.append({"tipo": tipo, "nivel": nivel, "proyecto_id": p.pk, "codigo": p.codigo, "nombre": p.nombre,
                          "estado": _nombre(p.estado, ""), "detalle": detalle})

    for p in lista:
        cerrado = bool(p.estado_id and p.estado.es_final)
        financiero = _pct(p.total_desembolsado, p.total_comprometido)
        fisico = float(p.ultimo_avance_fisico) if p.ultimo_avance_fisico is not None else None
        if p.total_desembolsado > p.total_comprometido:
            agregar(p, "Desembolsado mayor a lo comprometido", "alta",
                    f"Desembolsado Bs {p.total_desembolsado:,.2f} de Bs {p.total_comprometido:,.2f} comprometidos.")
        if cerrado:
            if p.pk not in con_seguimiento:
                agregar(p, "Cerrado sin medición de seguimiento", "media",
                        "No tiene mediciones «después» (producción, beneficiarios…) para comparar con la línea base.")
            continue
        if p.fecha_conclusion and p.fecha_conclusion < hoy:
            agregar(p, "Plazo vencido", "alta",
                    f"Debía concluir el {p.fecha_conclusion:%d/%m/%Y} ({(hoy - p.fecha_conclusion).days} días de atraso).")
        if p.fecha_orden_proceder and p.fecha_orden_proceder <= hoy:
            ultimo = ultimo_avance.get(p.pk)
            if ultimo is None:
                agregar(p, "Sin avance registrado", "media", f"Orden de proceder del {p.fecha_orden_proceder:%d/%m/%Y} y ningún avance físico cargado.")
            elif (hoy - ultimo).days > dias:
                agregar(p, "Sin avance reciente", "media", f"Último avance físico el {ultimo:%d/%m/%Y} (hace {(hoy - ultimo).days} días).")
        if financiero is not None and financiero - (fisico or 0) >= brecha:
            agregar(p, "Pagado por delante de lo ejecutado", "alta",
                    f"Avance financiero {financiero:.1f} % y físico {fisico or 0:.1f} %.")
    orden = {"alta": 0, "media": 1}
    return sorted(resultado, key=lambda a: (orden[a["nivel"]], a["tipo"], a["codigo"]))
