"""
Licencias ambientales (Fase 11, README de diseño §11): registro de todos los
trámites en circulación del área de Fiscalización. No se generan licencias.

- IRAP y Consultas de categoría son la misma tabla (`Tramite`); se distinguen
  por el tipo de documento (CNCA = consulta de categoría).
- Las listas (categorías y sus días, tipos de documento, tipos de ingreso)
  las define el Administrador de licencias en Configuración.
- Cada trámite guarda también el texto tal como se escribió (`texto_original`):
  si no coincide con la configuración, el campo queda vacío y el revisor de
  datos lo muestra para corregirlo (§11.6). No se adivina.
"""


from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from core.models import Catalogo, Persona
from core.texto import normalizar


class TipoDocumentoAmbiental(Catalogo):
    """IMA, MA, FNCA, CNCA, PPM-PASA, LASP…"""

    NINGUNA, ANUAL = "ninguna", "anual"
    PERIODICIDADES = [(NINGUNA, "Ninguna"), (ANUAL, "Anual")]

    sigla = models.CharField(max_length=30, blank=True)
    periodicidad = models.CharField(max_length=10, choices=PERIODICIDADES, default=NINGUNA,
                                    help_text="Anual: la AOP debe presentarlo cada gestión (alerta si falta).")
    es_consulta_categoria = models.BooleanField("es consulta de categoría", default=False,
                                                help_text="Sus trámites se muestran en la pestaña «Consultas de categoría».")

    class Meta(Catalogo.Meta):
        verbose_name = "tipo de documento ambiental"
        verbose_name_plural = "tipos de documento ambiental"


class Categoria(Catalogo):
    """Lista libre del área (CAT 4, CAT III, DAA, OBS, IMA…) con los días que dura cada una."""

    PRESENTACION, RESULTADO = "presentacion", "resultado"
    DESDE = [(PRESENTACION, "Fecha de presentación"), (RESULTADO, "Fecha del resultado")]

    dias = models.PositiveIntegerField("días", null=True, blank=True,
                                       help_text="Vacío = sin alerta de vencimiento.")
    contar_desde = models.CharField(max_length=12, choices=DESDE, default=PRESENTACION)
    dias_habiles = models.BooleanField("días hábiles", default=False,
                                       help_text="Sin sábados, domingos ni feriados (ver Feriados).")
    es_final = models.BooleanField("es final", default=False,
                                   help_text="El trámite terminó (no cuenta como pendiente).")

    class Meta(Catalogo.Meta):
        verbose_name = "categoría"
        verbose_name_plural = "categorías"


class TipoIngreso(Catalogo):
    """Inicio, Reingreso, Reinicio, Fuera de plazo, Renovación…"""

    class Meta(Catalogo.Meta):
        verbose_name = "tipo de ingreso"
        verbose_name_plural = "tipos de ingreso"


class AOP(models.Model):
    """Actividad, obra o proyecto que presenta los documentos ambientales."""

    nombre = models.CharField(max_length=300)
    clave = models.CharField(max_length=300, editable=False, db_index=True)
    municipios = models.ManyToManyField("territorio.Municipio", blank=True, related_name="aops",
                                        help_text="Una AOP puede abarcar varios municipios.")
    representante = models.ForeignKey(Persona, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                      verbose_name="representante legal")
    consultor = models.ForeignKey(Persona, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    eliminado = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords(m2m_fields=[municipios])

    class Meta:
        verbose_name = "AOP"
        verbose_name_plural = "AOP"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.nombre = " ".join(self.nombre.split())
        self.clave = normalizar(self.nombre)
        super().save(*args, **kwargs)


class Tramite(models.Model):
    # Dos números (D32): el id interno no cambia nunca; el «número» del folder se corrige y puede repetirse.
    numero = models.CharField("número", max_length=40, blank=True, help_text="Número del folder (editable).")
    numero_asignado = models.CharField("número asignado", max_length=100, blank=True)
    aop = models.ForeignKey(AOP, on_delete=models.PROTECT, related_name="tramites", verbose_name="AOP")
    tipo_documento = models.ForeignKey(TipoDocumentoAmbiental, on_delete=models.PROTECT, null=True, blank=True,
                                       related_name="tramites", verbose_name="tipo de documento")
    gestion_documento = models.CharField("gestión del documento", max_length=30, blank=True,
                                         help_text="Ej. 2025-2026 (IMA).")
    fecha_presentacion = models.DateField("fecha de presentación", null=True, blank=True)
    tipo_ingreso = models.ForeignKey(TipoIngreso, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="tramites", verbose_name="tipo de ingreso")
    tecnico = models.CharField("técnico", max_length=100, blank=True)
    legal = models.CharField(max_length=100, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, null=True, blank=True, related_name="tramites",
                                  verbose_name="categoría / resultado")
    fecha_resultado = models.DateField("fecha del resultado", null=True, blank=True,
                                       help_text="Elaboración de la nota o licencia.")
    entregado = models.BooleanField(default=False)
    fecha_recepcion = models.DateField("fecha de recepción", null=True, blank=True)
    nro_recepcion = models.CharField("n.º de recepción", max_length=40, blank=True)
    observaciones = models.TextField(blank=True)
    proyecto = models.ForeignKey("proyectos.Proyecto", on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="tramites", help_text="Opcional: un proyecto puede tener muchos trámites.")
    texto_original = models.JSONField(default=dict, blank=True, editable=False,
                                      help_text="Valores tal como se escribieron (importación, grilla o migración).")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                       editable=False, related_name="+")
    eliminado = models.BooleanField(default=False, help_text="Papelera (borrado lógico).")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "trámite"
        verbose_name_plural = "trámites"
        ordering = ["-fecha_presentacion", "-id"]

    def __str__(self):
        return f"{self.numero or f'#{self.pk}'} – {self.aop}"

    def clean(self):
        if self.fecha_presentacion and self.fecha_resultado and self.fecha_resultado < self.fecha_presentacion:
            raise ValidationError({"fecha_resultado": "No puede ser anterior a la fecha de presentación."})

    @property
    def vencimiento(self):
        from .plazos import vencimiento

        return vencimiento(self)


class Equivalencia(models.Model):
    """«cbba» → Cochabamba, «cat4» → CAT 4: las define el área en el revisor de datos (§11.6)."""

    CAMPOS = [("municipio", "Municipio"), ("tipo_documento", "Tipo de documento"), ("categoria", "Categoría"),
              ("tipo_ingreso", "Tipo de ingreso"), ("tecnico", "Técnico"), ("legal", "Legal")]

    campo = models.CharField(max_length=20, choices=CAMPOS)
    texto = models.CharField(max_length=200, help_text="Texto normalizado (sin mayúsculas ni tildes).")
    valor_id = models.PositiveIntegerField(null=True, blank=True, help_text="Para listas configuradas.")
    valor_texto = models.CharField(max_length=100, blank=True, help_text="Para técnico y legal (texto).")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "equivalencia"
        verbose_name_plural = "equivalencias"
        constraints = [models.UniqueConstraint(fields=["campo", "texto"], name="licencias_equivalencia_unica")]

    def save(self, *args, **kwargs):
        self.texto = normalizar(self.texto)
        super().save(*args, **kwargs)


class Feriado(models.Model):
    fecha = models.DateField(unique=True)
    nombre = models.CharField(max_length=100)

    class Meta:
        verbose_name = "feriado"
        verbose_name_plural = "feriados"
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.fecha:%d/%m/%Y} – {self.nombre}"


# Columnas de la tabla principal (clave, título). Las que ve el funcionario son configurables.
COLUMNAS = [
    ("id", "ID"), ("numero", "Número"), ("municipios", "Municipio"), ("numero_asignado", "Número asignado"),
    ("fecha_presentacion", "Fecha de presentación"), ("mes", "Mes"), ("anio", "Año"), ("aop", "AOP"),
    ("tipo_documento", "Tipo de documento"), ("gestion_documento", "Gestión del documento"),
    ("representante", "Representante legal"), ("consultor", "Consultor"), ("telefono", "Teléfono"),
    ("tipo_ingreso", "Tipo de ingreso"), ("tecnico", "Técnico"), ("legal", "Legal"),
    ("categoria", "Categoría / resultado"), ("fecha_resultado", "Fecha del resultado"), ("entregado", "Entregado"),
    ("fecha_recepcion", "Fecha de recepción"), ("nro_recepcion", "N.º de recepción"), ("vencimiento", "Vence"),
    ("observaciones", "Observaciones"), ("proyecto", "Proyecto"), ("registrado_por", "Registrado por"),
]
# Las mismas que el «Funcionario» veía en la app de Apps Script (sin técnico, legal, resultado ni firma).
COLUMNAS_FUNCIONARIO_INICIALES = ["id", "numero", "municipios", "numero_asignado", "fecha_presentacion", "mes", "anio",
                                  "aop", "tipo_documento", "representante", "consultor", "telefono"]


def _columnas_iniciales():
    return list(COLUMNAS_FUNCIONARIO_INICIALES)


class ConfiguracionLicencias(models.Model):
    """Un solo registro con la configuración general del módulo."""

    dias_aviso = models.PositiveIntegerField("días de aviso", default=5,
                                             help_text="Cuántos días antes del vencimiento se avisa «por vencer».")
    columnas_funcionario = models.JSONField("columnas que ve el funcionario", default=_columnas_iniciales)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "configuración de licencias"
        verbose_name_plural = "configuración de licencias"

    def __str__(self):
        return "Configuración de licencias"

    @classmethod
    def actual(cls):
        return cls.objects.first() or cls.objects.create()


class PreferenciaColumnas(models.Model):
    """Columnas que cada usuario eligió ver en la tabla (dentro de las que le permite su rol)."""

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="columnas_licencias")
    columnas = models.JSONField(default=list)

    class Meta:
        verbose_name = "columnas elegidas"
        verbose_name_plural = "columnas elegidas"
