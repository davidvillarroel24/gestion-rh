"""
Datos mínimos de arranque (D18: los demás catálogos crecen con el uso).

- Unidades: las 7 hojas UD_* del sistema anterior (Motor SIG). Se pueden
  renombrar o desactivar desde la administración.
- Tipos de fuente de financiamiento: Externo, Gobernación, Municipio (D10).
"""

from django.db import migrations

from core.texto import normalizar

UNIDADES = [
    "Riego",
    "Residuos Sólidos",
    "Forestación",
    "Cuencas",
    "Gestión de Riesgos",
    "Fiscalización",
    "Biodiversidad",
]

TIPOS_FUENTE = ["Externo", "Gobernación", "Municipio"]


def cargar(apps, schema_editor):
    for modelo, nombres in (("Unidad", UNIDADES), ("TipoFuente", TIPOS_FUENTE)):
        clase = apps.get_model("core", modelo)
        for nombre in nombres:
            clase.objects.get_or_create(clave=normalizar(nombre), defaults={"nombre": nombre})


class Migration(migrations.Migration):
    dependencies = [("core", "0002_initial")]

    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
