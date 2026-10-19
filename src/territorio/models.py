"""
Límites territoriales del departamento de Cochabamba.

El MUNICIPIO es la única fuente de geometría. Provincia y Región guardan una
geometría DERIVADA (unión de sus municipios), recalculada por
territorio.servicios.recalcular_agregados() — no se edita a mano.

La región es atributo del municipio, no de la provincia: una misma provincia
puede tener municipios en regiones distintas (Chapare: Sacaba es
Metropolitana y Villa Tunari es Trópico).
"""

from django.contrib.gis.db import models
from simple_history.models import HistoricalRecords


class Region(models.Model):
    nombre = models.CharField(max_length=60, unique=True)
    geom = models.MultiPolygonField(srid=4326, null=True, blank=True, help_text="Derivada de sus municipios.")

    class Meta:
        verbose_name = "región"
        verbose_name_plural = "regiones"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Provincia(models.Model):
    codigo = models.CharField(max_length=4, unique=True, help_text="Código INE (departamento + provincia), ej. 0310.")
    nombre = models.CharField(max_length=60, unique=True)
    geom = models.MultiPolygonField(srid=4326, null=True, blank=True, help_text="Derivada de sus municipios.")

    class Meta:
        verbose_name = "provincia"
        verbose_name_plural = "provincias"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Municipio(models.Model):
    codigo_ine = models.CharField(
        max_length=6, unique=True, null=True, blank=True,
        help_text="Código INE de 6 dígitos. Vacío si aún no tiene uno oficial (ej. TIOC nuevas).",
    )
    nombre = models.CharField(max_length=80, unique=True)
    es_tioc = models.BooleanField("TIOC", default=False, help_text="Territorio Indígena Originario Campesino.")
    provincia = models.ForeignKey(Provincia, on_delete=models.PROTECT, related_name="municipios")
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="municipios")
    geom = models.MultiPolygonField(srid=4326)

    # Auditoría: queda registro de cada cambio de límites (quién, cuándo, valor anterior).
    history = HistoricalRecords()

    class Meta:
        verbose_name = "municipio"
        verbose_name_plural = "municipios"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
