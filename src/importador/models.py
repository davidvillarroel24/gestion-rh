"""
Registro de importaciones (README de diseño §8): cada carga queda guardada con
su archivo, su resultado y la lista de cambios que hizo, para poder revertirla.
"""

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Importacion(models.Model):
    TABULAR, ESPACIAL = "tabular", "espacial"
    TIPOS = [(TABULAR, "Excel / CSV"), (ESPACIAL, "Mapa (KML, KMZ, GeoJSON, SHP)")]

    PENDIENTE, CON_ERRORES, VALIDADA, APLICADA, REVERTIDA = "pendiente", "con_errores", "validada", "aplicada", "revertida"
    ESTADOS = [
        (PENDIENTE, "Pendiente de opciones"),
        (CON_ERRORES, "Con errores"),
        (VALIDADA, "Validada (lista para confirmar)"),
        (APLICADA, "Aplicada"),
        (REVERTIDA, "Revertida"),
    ]

    tipo = models.CharField(max_length=10, choices=TIPOS)
    destino = models.CharField(max_length=40, help_text="Tabla (importación tabular) o destino espacial.")
    archivo = models.FileField(upload_to="importaciones/%Y/%m/")
    nombre_archivo = models.CharField(max_length=255)
    opciones = models.JSONField(default=dict, blank=True)
    estado = models.CharField(max_length=12, choices=ESTADOS, default=PENDIENTE)
    resumen = models.JSONField(default=dict, blank=True, help_text="Conteos, errores y avisos del último proceso.")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="importaciones")
    creada_en = models.DateTimeField(auto_now_add=True)
    aplicada_en = models.DateTimeField(null=True, blank=True)
    revertida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "importación"
        verbose_name_plural = "importaciones"
        ordering = ["-creada_en"]

    def __str__(self):
        return f"{self.get_tipo_display()} – {self.nombre_archivo} ({self.get_estado_display()})"


class Cambio(models.Model):
    """Lo que hizo una importación aplicada, en orden, para poder deshacerlo."""

    CREADO, ACTUALIZADO, RELACION = "creado", "actualizado", "relacion"
    ACCIONES = [(CREADO, "Creado"), (ACTUALIZADO, "Actualizado"), (RELACION, "Relación agregada")]

    importacion = models.ForeignKey(Importacion, on_delete=models.CASCADE, related_name="cambios")
    tipo_contenido = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    objeto_id = models.PositiveBigIntegerField()
    accion = models.CharField(max_length=12, choices=ACCIONES)
    # Para ACTUALIZADO: versión del historial antes y después de la importación.
    version_previa = models.PositiveBigIntegerField(null=True, blank=True)
    version_importada = models.PositiveBigIntegerField(null=True, blank=True)
    # Para RELACION: datos de la relación agregada (ej. {"municipio": 12}).
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["id"]
