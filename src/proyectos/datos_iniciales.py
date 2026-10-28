"""
Valores iniciales de los catálogos, tomados del sistema anterior
(Version appscript/googlesheet drive/SDMAyRH Centralizador.xlsx), unificando
variantes y errores de tipeo. Lo que el Excel no tenía (tipos de elemento,
tipos de evento) sale de lo acordado en el diseño.

Se cargan con: python manage.py cargar_catalogos
Después los catálogos siguen creciendo con el uso (D18).
"""

from proyectos.models import TipoElemento

PUNTO, LINEA, POLIGONO = TipoElemento.PUNTO, TipoElemento.LINEA, TipoElemento.POLIGONO

# UD_RIEGOS.ESTADO_DEL_PROYECTO (en orden de ciclo de vida)
ESTADOS_FINALES = {"Concluido", "De baja"}  # proyecto cerrado: sin alertas de plazo ni de avance
ESTADOS = [
    "Con convenio",                # "se cuenta con convenio"
    "En licitación",
    "Sin ejecución",
    "En ejecución",
    "En balance de obra inicial",
    "Concluido",
    "De baja",
]

# Por unidad (clave normalizada de la unidad -> valores)
PROGRAMAS = {
    "riego": [
        "Programa Seguridad Alimentaria",
        "PRONAREC III",            # unifica "PROMAREC III" (error de tipeo, 6 filas)
        "Mi Riego",
        "Mi Riego II",
        "Mi Agua",
        "PACC I",                  # UD_RIEGOS.TRANSFERENCIA
        "PACC II",
        "PPCR",
    ],
}

TIPOS_PROYECTO = {
    "riego": [
        "Proyecto menor",
        "Proyecto mediano",
        "Proyecto mayor",
        "Agua potable",
        "PTAR",
        # Componentes del Programa Seguridad Alimentaria (hojas TANQUES/UGR/GEOMEMBRANA)
        "Tanques",
        "UGR",
        "Geomembrana",
    ],
}

TIPOS_ELEMENTO = {
    "riego": [
        ("Toma de agua", PUNTO),
        ("Bombeo", PUNTO),
        ("Atajado", PUNTO),
        ("Cámara", PUNTO),
        ("Tanque", PUNTO),
        ("Pozo", PUNTO),
        ("Canal", LINEA),
        ("Aducción", LINEA),
        ("Área de riego", POLIGONO),
    ],
    "forestacion": [
        ("Punto de plantación", PUNTO),
        ("Área forestada", POLIGONO),
    ],
    "residuos solidos": [
        ("Botadero", PUNTO),
        ("Relleno sanitario", PUNTO),
        ("Área del botadero", POLIGONO),
    ],
    "gestion de riesgos": [
        ("Incendio", PUNTO),
        ("Área quemada", POLIGONO),
        ("Zona inundada", POLIGONO),
    ],
}

# UD_RIEGOS.ENTIDAD_EJECUTORA (más la Gobernación). Los gobiernos municipales
# se crean aparte, uno por municipio (ver el comando).
ENTIDADES = [
    ("GADC – Gobernación de Cochabamba", "gobernacion"),
    ("FPS", "externo"),
    ("EMAGUA", "externo"),
    ("PPCR", "externo"),
]

# Bitácora (diseño §6.2)
TIPOS_EVENTO = [
    "Cambio de estado",
    "Observación",
    "Paralización",
    "Reanudación",
    "Ampliación de plazo",
    "Visita de seguimiento",
    "Incidencia",
]

# Columnas de cantidades del Excel que pasan a ser materiales e indicadores
MATERIALES = [("Cemento", "bolsas"), ("Fierro", "barras"), ("Geomembrana", "m²")]

INDICADORES = [
    ("Familias beneficiadas", "familias", "beneficiarios"),   # FAMILIAS_BENEFICIADA
    ("Personas beneficiadas", "personas", "beneficiarios"),
    ("Área de riego", "ha", "fisico"),                         # AREA_DE_RIEGO
    ("Área plantada", "ha", "fisico"),                         # AREA_PLANTADA_HA
    ("Plantines", "plantines", "fisico"),                      # PLANTINES
    ("Área del botadero", "ha", "fisico"),                     # Residuos AREA_HA
]

DESAGREGACIONES = ["Hombres", "Mujeres"]

# UD_FORESTACIONES.PROPOSITO ("SIN CLASIFICAR" queda vacío)
PROPOSITOS = [
    "Comercial",
    "Protección y restauración de fuentes de agua y suelos",
    "Mixto (comercial / protección)",
    "Restauración",
]

# UD_FORESTACIONES.TIPO_PLANTA (separando combinaciones como "JACARANDA / MOLLE")
TIPOS_PLANTA = [
    "Pino radiata", "Pino patula", "Pino ciprés", "Nativo", "Kewiña", "Tara",
    "Aliso", "Guayaba", "Jacarandá", "Molle", "Jarka",
]
