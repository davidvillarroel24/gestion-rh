"""
Núcleo compartido por todos los módulos (proyectos, licencias…):
usuarios con su alcance, catálogos que crecen con el uso, entidades y personas.

Los catálogos no se precargan (salvo unidades y tipos de fuente): se crean
desde los formularios a medida que se usan. Cada valor guarda una `clave`
normalizada única, así que "Cochabamba" y "COCHABAMBA " no pueden coexistir.
"""

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from .texto import normalizar, similitud

UMBRAL_PARECIDO = 0.8


class Catalogo(models.Model):
    nombre = models.CharField(max_length=120)
    clave = models.CharField(max_length=120, unique=True, editable=False)
    activo = models.BooleanField(default=True, help_text="Desactivar en lugar de borrar: los registros que lo usan se conservan.")

    history = HistoricalRecords(inherit=True)

    class Meta:
        abstract = True
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.nombre = " ".join(self.nombre.split())
        self.clave = normalizar(self.nombre)
        super().save(*args, **kwargs)

    def clean(self):
        clave = normalizar(self.nombre)
        if not clave:
            raise ValidationError({"nombre": "El nombre no puede quedar vacío."})
        repetido = type(self).objects.filter(clave=clave).exclude(pk=self.pk).first()
        if repetido:
            raise ValidationError({"nombre": f"Ya existe «{repetido.nombre}»."})

    @classmethod
    def parecidos(cls, nombre, excluir_pk=None, limite=5):
        """Valores existentes que se parecen a `nombre` (para avisar antes de crear uno nuevo)."""
        clave = normalizar(nombre)
        candidatos = []
        for obj in cls.objects.exclude(pk=excluir_pk):
            puntaje = similitud(clave, obj.clave)
            if puntaje >= UMBRAL_PARECIDO:
                candidatos.append((puntaje, obj))
        candidatos.sort(key=lambda par: -par[0])
        return [obj for _, obj in candidatos[:limite]]


class Unidad(Catalogo):
    """Unidad organizacional de la Secretaría (Riego, Residuos Sólidos, Forestación…)."""

    class Meta(Catalogo.Meta):
        verbose_name = "unidad"
        verbose_name_plural = "unidades"


class TipoFuente(Catalogo):
    """Origen del financiamiento: Externo, Gobernación, Municipio."""

    class Meta(Catalogo.Meta):
        verbose_name = "tipo de fuente"
        verbose_name_plural = "tipos de fuente"


class TipoDocumento(Catalogo):
    class Meta(Catalogo.Meta):
        verbose_name = "tipo de documento"
        verbose_name_plural = "tipos de documento"


class TipoEvento(Catalogo):
    """Para la bitácora: cambio de estado, observación, paralización, ampliación de plazo…"""

    class Meta(Catalogo.Meta):
        verbose_name = "tipo de evento"
        verbose_name_plural = "tipos de evento"


class Entidad(Catalogo):
    """Quien financia o ejecuta: la Gobernación, un GAM (con su municipio) o un financiador externo."""

    tipo_fuente = models.ForeignKey(TipoFuente, on_delete=models.PROTECT, related_name="entidades")
    municipio = models.ForeignKey(
        "territorio.Municipio", on_delete=models.PROTECT, null=True, blank=True, related_name="entidades",
        help_text="Solo para gobiernos municipales (contraparte municipal).",
    )

    class Meta(Catalogo.Meta):
        verbose_name = "entidad"
        verbose_name_plural = "entidades"


class Persona(models.Model):
    """Representantes legales, consultores, contactos. Puede haber homónimos: no se fuerza unicidad por nombre."""

    nombre = models.CharField(max_length=150)
    ci = models.CharField("CI", max_length=20, unique=True, null=True, blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    correo = models.EmailField(blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "persona"
        verbose_name_plural = "personas"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.ci})" if self.ci else self.nombre

    def save(self, *args, **kwargs):
        self.nombre = " ".join(self.nombre.split())
        self.ci = (self.ci or "").strip() or None
        super().save(*args, **kwargs)


class Usuario(AbstractUser):
    """
    Usuario del sistema. El ROL viene de su grupo (ver core/roles.py); el ALCANCE,
    de las unidades y municipios asignados acá (ver core/alcance.py).
    """

    unidades = models.ManyToManyField(Unidad, blank=True, related_name="usuarios",
                                      help_text="Para técnicos de unidad: unidades que gestiona.")
    municipios = models.ManyToManyField("territorio.Municipio", blank=True, related_name="usuarios",
                                        help_text="Para encargados municipales: municipios que atiende.")

    history = HistoricalRecords(excluded_fields=["password", "last_login"], m2m_fields=[unidades, municipios])

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.get_full_name() or self.username
