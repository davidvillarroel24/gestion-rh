"""
Montos en letras, como se escriben en las fichas y convenios:
1834440 -> "Un Millón Ochocientos Treinta y Cuatro Mil Cuatrocientos Cuarenta con 00/100 Bolivianos".
"""

from decimal import ROUND_HALF_UP, Decimal

UNIDADES = ["", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
            "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte",
            "veintiuno", "veintidós", "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete",
            "veintiocho", "veintinueve"]
DECENAS = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"]
CENTENAS = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos",
            "ochocientos", "novecientos"]


def _menor_de_mil(n):
    if n == 100:
        return "cien"
    centena, resto = divmod(n, 100)
    partes = [CENTENAS[centena]] if centena else []
    if resto < 30:
        partes.append(UNIDADES[resto])
    else:
        decena, unidad = divmod(resto, 10)
        partes.append(DECENAS[decena] + (f" y {UNIDADES[unidad]}" if unidad else ""))
    return " ".join(p for p in partes if p)


def _apocopar(texto):
    """'veintiuno mil' -> 'veintiún mil', 'uno millones' no ocurre: delante de mil/millón 'uno' pasa a 'un'."""
    if texto.endswith("veintiuno"):
        return texto[:-len("veintiuno")] + "veintiún"
    if texto.endswith("uno"):
        return texto[:-3] + "un"
    return texto


def entero_en_letras(n):
    if n == 0:
        return "cero"
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    partes = []
    if millones:
        partes.append("un millón" if millones == 1 else f"{_apocopar(entero_en_letras(millones))} millones")
    if miles:
        partes.append("mil" if miles == 1 else f"{_apocopar(_menor_de_mil(miles))} mil")
    if unidades:
        partes.append(_menor_de_mil(unidades))
    return " ".join(partes)


def bolivianos(monto):
    """Monto con centavos en formato de documento oficial (cada palabra con mayúscula, salvo 'y' y 'con')."""
    monto = Decimal(str(monto or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    entero = int(monto)
    centavos = int((monto - entero) * 100)
    palabras = " ".join(p if p == "y" else p.capitalize() for p in entero_en_letras(entero).split())
    return f"{palabras} con {centavos:02d}/100 Bolivianos"
