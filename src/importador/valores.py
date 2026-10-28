"""
Conversión de celdas (Excel o CSV) a valores de Python, tolerante con los
formatos que usa la gente: "1.234,56", "15/03/2026", "Sí", celdas de fecha de Excel…
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from core.texto import normalizar


class ErrorValor(ValueError):
    pass


def vacio(valor):
    return valor is None or (isinstance(valor, str) and not valor.strip())


def texto(valor):
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)  # Excel guarda "123" como 123.0
    return " ".join(str(valor).split())


def decimal(valor):
    if isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool):
        return Decimal(str(valor))
    s = str(valor).strip().replace(" ", "").replace("Bs", "").replace("%", "")
    if "," in s and "." in s:      # 1.234,56 (es-BO)
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                 # 1234,56
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise ErrorValor(f"«{valor}» no es un número.")


def entero(valor):
    d = decimal(valor)
    if d != d.to_integral_value():
        raise ErrorValor(f"«{valor}» debe ser un número entero.")
    return int(d)


def fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    s = str(valor).strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, formato).date()
        except ValueError:
            continue
    raise ErrorValor(f"«{valor}» no es una fecha (use dd/mm/aaaa).")


def booleano(valor):
    if isinstance(valor, bool):
        return valor
    n = normalizar(valor)
    if n in ("si", "s", "1", "verdadero", "true", "x"):
        return True
    if n in ("no", "n", "0", "falso", "false"):
        return False
    raise ErrorValor(f"«{valor}» debe ser Sí o No.")


def opcion(valor, opciones):
    """opciones: [(valor_interno, etiqueta)]. Acepta la etiqueta o el valor interno."""
    n = normalizar(valor)
    for interno, etiqueta in opciones:
        if n in (normalizar(etiqueta), normalizar(interno)):
            return interno
    raise ErrorValor(f"«{valor}» no es válido. Opciones: {', '.join(e for _, e in opciones)}.")


def sin_html(texto_error):
    return re.sub(r"<[^>]+>", "", str(texto_error))
