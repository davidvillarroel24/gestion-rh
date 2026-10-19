"""Normalización de texto para detectar duplicados en catálogos.

"Cochabamba", "COCHABAMBA " y "cochabamba." deben ser el mismo valor; así se
evita el problema del sistema anterior (63 formas de escribir 47 municipios).
"""

import re
import unicodedata
from difflib import SequenceMatcher


def normalizar(texto):
    """Minúsculas, sin tildes, sin signos y con espacios simples."""
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^0-9a-zA-Z]+", " ", texto.lower())
    return " ".join(texto.split())


def similitud(a, b):
    """0..1 entre dos textos ya normalizados (1 = iguales)."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(min(a, b, key=len)) >= 4 and (a in b or b in a):
        return 0.9
    return SequenceMatcher(None, a, b).ratio()
