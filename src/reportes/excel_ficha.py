"""
Ficha técnica en Excel con el formato de `Ficha tecnica/1FICHA TECNICA.xlsx`:
columnas A–F, etiquetas en A:B, contenido en C:F, Arial, bordes finos, una hoja
por ficha y área de impresión ajustada a una página de ancho.
"""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

ANCHOS = {"A": 22.9, "B": 11.1, "C": 15.7, "D": 17.0, "E": 24.1, "F": 53.1}
FINA = Side(style="thin")
BORDE = Border(left=FINA, right=FINA, top=FINA, bottom=FINA)
CENTRO = Alignment(horizontal="center", vertical="center", wrap_text=True)
IZQUIERDA = Alignment(horizontal="left", vertical="center", wrap_text=True)
DERECHA = Alignment(horizontal="right", vertical="center", wrap_text=True)


class _Hoja:
    def __init__(self, hoja):
        self.hoja = hoja
        self.fila = 1
        for letra, ancho in ANCHOS.items():
            hoja.column_dimensions[letra].width = ancho

    def celda(self, rango, valor, tamano=12, negrita=True, alineacion=CENTRO, alto=None):
        primera = rango.split(":")[0]
        if ":" in rango:
            self.hoja.merge_cells(rango)
        c = self.hoja[primera]
        c.value = valor
        c.font = Font(name="Arial", size=tamano, bold=negrita)
        c.alignment = alineacion
        celdas = self.hoja[rango] if ":" in rango else ((c,),)  # un rango da filas de celdas; una celda, la celda
        for fila in celdas:
            for x in fila:
                x.border = BORDE
        if alto:
            self.hoja.row_dimensions[int("".join(ch for ch in primera if ch.isdigit()))].height = alto

    def etiqueta(self, texto, filas=1, tamano=14):
        self.celda(f"A{self.fila}:B{self.fila + filas - 1}", texto, tamano)


def _llenar(h, f):
    h.hoja.merge_cells("A1:F1")
    titulo = h.hoja["A1"]
    titulo.value, titulo.font, titulo.alignment = "FICHA TÉCNICA", Font(name="Arial", size=22, bold=True), CENTRO
    h.celda("A2:F2", f["titulo"].upper(), 18, alto=65)
    h.fila = 3

    if f["proyecto"]:
        p = f["proyecto"]
        detalle = " · ".join(x for x in [p.codigo, p.estado.nombre if p.estado_id else "", p.programa.nombre if p.programa_id else "",
                                         f"Gestión {p.gestion}" if p.gestion else "", p.comunidad] if x)
        h.etiqueta("PROYECTO:")
        h.celda(f"C{h.fila}:F{h.fila}", detalle, 12, negrita=False, alto=36)
        h.fila += 1

    h.etiqueta("UBICACIÓN POLÍTICA")
    ubicacion = (f"Departamento de Cochabamba\nProvincias: {', '.join(f['provincias'])}\n"
                 f"Municipios ({len(f['municipios'])}): {', '.join(f['municipios'])}")
    h.celda(f"C{h.fila}:F{h.fila}", ubicacion, 12, negrita=False, alineacion=IZQUIERDA,
            alto=max(60, 15 * (3 + len(", ".join(f["municipios"])) // 90)))
    h.fila += 1

    h.etiqueta("POBLACIÓN :")
    poblacion = "\n".join(x["beneficiarios"] + (" (incluye metas)" if x["incluye_metas"] else "") for x in f["poblacion"]) or "—"
    h.celda(f"C{h.fila}:F{h.fila}", poblacion, 18, alto=24 * max(1, len(f["poblacion"])))
    h.fila += 1

    inicio = h.fila
    for i, a in enumerate(f["acciones"], start=1):
        lineas = [f"• Cantidad: {a['cantidad']} {'proyecto' if a['cantidad'] == 1 else 'proyectos'}"]
        lineas += [f"• {x['nombre']}: {x['texto']}" for x in a["materiales"] + a["indicadores"]]
        primera = h.fila
        for linea in lineas:
            h.celda(f"F{h.fila}", linea, 14, alineacion=IZQUIERDA, alto=26)
            h.fila += 1
        h.celda(f"C{primera}:E{h.fila - 1}", f"{i}.  {a['tipo']}", 12)
        h.celda(f"C{h.fila}:E{h.fila}", "MUNICIPIOS BENEFICIADOS: ", 14, alineacion=DERECHA)
        h.celda(f"F{h.fila}", f"{a['municipios']} {'MUNICIPIO' if a['municipios'] == 1 else 'MUNICIPIOS'}", 16, alto=28)
        h.fila += 1
    if f["acciones"]:
        h.celda(f"A{inicio}:B{h.fila - 1}", "ACCIONES: ", 14)

    h.etiqueta("OBJETIVO:")
    h.celda(f"C{h.fila}:F{h.fila}", f["objetivo"] or "", 14, negrita=False, alto=max(40, 18 * (1 + len(f["objetivo"]) // 80)))
    h.fila += 1

    for c in f["costos"]:
        h.etiqueta(f"COSTO {c['fuente'].upper()}:", filas=2)
        h.celda(f"C{h.fila}:F{h.fila}", f"{c['monto_texto']} Bs ({c['letras']}).", 16, alto=52)
        h.celda(f"C{h.fila + 1}:F{h.fila + 1}", f"{c['porcentaje']} % {c['fuente'].upper()}", 16, alto=30)
        h.fila += 2
    if not f["costos"]:
        h.etiqueta("COSTO DE LA INVERSIÓN:")
        h.celda(f"C{h.fila}:F{h.fila}", "Sin financiamiento registrado", 14, negrita=False, alto=30)
        h.fila += 1

    h.etiqueta("TOTAL:", tamano=22)
    h.celda(f"C{h.fila}:F{h.fila}", f"{f['total_texto']} Bs ({f['total_letras']})" if f["total"] else "—", 18, alto=63)

    h.hoja.print_area = f"A1:F{h.fila}"
    h.hoja.page_setup.orientation = "portrait"
    h.hoja.page_setup.fitToWidth, h.hoja.page_setup.fitToHeight = 1, 0
    h.hoja.sheet_properties.pageSetUpPr.fitToPage = True


def libro(fichas):
    salida = Workbook()
    salida.remove(salida.active)
    for i, f in enumerate(fichas, start=1):
        nombre = (f["proyecto"].codigo if f["proyecto"] and len(fichas) > 1 else "Ficha técnica")[:31]
        _llenar(_Hoja(salida.create_sheet(nombre if len(fichas) == 1 or f["proyecto"] else f"Ficha {i}")), f)
    if not fichas:
        salida.create_sheet("Ficha técnica")["A1"] = "No hay proyectos con esos filtros."
    return salida
