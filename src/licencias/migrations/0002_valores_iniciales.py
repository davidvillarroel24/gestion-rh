"""
Valores iniciales tomados de la planilla «RECEPCIÓN UCyFA» (los más usados, ya unificados).
Las categorías NO se precargan: las escribe el área con sus días (D32). Todo se puede
corregir, desactivar o ampliar en /licencias/configuracion/.
"""

from django.db import migrations

from core.texto import normalizar

TIPOS_INGRESO = ["Inicio", "Reingreso", "Reinicio", "Fuera de plazo", "Renovación"]
# (nombre, sigla, periodicidad, es_consulta_categoria)
TIPOS_DOCUMENTO = [
    ("Informe de Monitoreo Ambiental", "IMA", "anual", False),
    ("Manifiesto Ambiental", "MA", "ninguna", False),
    ("Formulario de Nivel de Categorización Ambiental", "FNCA", "ninguna", False),
    ("Consulta de Nivel de Categorización Ambiental", "CNCA", "ninguna", True),
    ("Programa de Prevención y Mitigación – Plan de Aplicación y Seguimiento Ambiental", "PPM-PASA", "ninguna", False),
    ("Licencia para Actividades con Sustancias Peligrosas", "LASP", "ninguna", False),
    ("Informe Ambiental Anual", "IAA", "anual", False),
]


def cargar(apps, schema_editor):
    TipoIngreso = apps.get_model("licencias", "TipoIngreso")
    TipoDocumento = apps.get_model("licencias", "TipoDocumentoAmbiental")
    Configuracion = apps.get_model("licencias", "ConfiguracionLicencias")
    for nombre in TIPOS_INGRESO:
        TipoIngreso.objects.get_or_create(clave=normalizar(nombre), defaults={"nombre": nombre})
    for nombre, sigla, periodicidad, consulta in TIPOS_DOCUMENTO:
        TipoDocumento.objects.get_or_create(clave=normalizar(nombre), defaults={
            "nombre": nombre, "sigla": sigla, "periodicidad": periodicidad, "es_consulta_categoria": consulta})
    if not Configuracion.objects.exists():
        Configuracion.objects.create()


class Migration(migrations.Migration):
    dependencies = [("licencias", "0001_initial")]
    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
