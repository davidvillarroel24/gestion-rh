"""
Proyectos de la Secretaría (README de diseño §6, en 3FN).

Reglas que el modelo garantiza:
- Un proyecto puede abarcar varios municipios (D6); región y provincia salen
  del municipio, no se guardan en el proyecto.
- El dinero vive una sola vez (D10): compromiso por entidad (Financiamiento) y
  pagos contra ese compromiso (Desembolso). Costo total, desembolsado y avance
  financiero se CALCULAN, no se guardan.
- Varias geometrías por proyecto, cada una con su tipo de elemento (D8).
- Beneficiarios, hectáreas y producción antes/después son Mediciones de
  Indicadores (D7): agregar uno nuevo no cambia la base de datos.
- El estado actual lo cambia la bitácora (Evento), así queda su historia.
- Documentos opcionales (D13), solo consulta y descarga (D20).
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.gis.db import models
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Sum
from django.db.models.signals import post_delete
from django.dispatch import receiver
from simple_history.models import HistoricalRecords

from core.models import Catalogo, CatalogoPorUnidad, Entidad, TipoDocumento, TipoEvento, Unidad
from territorio.models import Municipio

DINERO = {"max_digits": 14, "decimal_places": 2}
CERO = Decimal("0")


# ---------------------------------------------------------------- catálogos


class EstadoProyecto(Catalogo):
    orden = models.PositiveSmallIntegerField(default=0, help_text="Orden en listas y gráficas.")

    class Meta(Catalogo.Meta):
        verbose_name = "estado de proyecto"
        verbose_name_plural = "estados de proyecto"
        ordering = ["orden", "nombre"]


class Programa(CatalogoPorUnidad):
    class Meta(CatalogoPorUnidad.Meta):
        verbose_name = "programa"
        verbose_name_plural = "programas"


class TipoProyecto(CatalogoPorUnidad):
    class Meta(CatalogoPorUnidad.Meta):
        verbose_name = "tipo de proyecto"
        verbose_name_plural = "tipos de proyecto"


class TipoElemento(CatalogoPorUnidad):
    """Qué representa cada geometría: toma de agua, área de riego, bombeo, atajado, cámara, canal…"""

    PUNTO, LINEA, POLIGONO = "Point", "LineString", "Polygon"
    TIPOS_GEOMETRIA = [(PUNTO, "Punto"), (LINEA, "Línea"), (POLIGONO, "Polígono")]

    tipo_geometria = models.CharField(max_length=12, choices=TIPOS_GEOMETRIA)

    class Meta(CatalogoPorUnidad.Meta):
        verbose_name = "tipo de elemento"
        verbose_name_plural = "tipos de elemento"


class Indicador(Catalogo):
    BENEFICIARIOS, PRODUCTIVO, FISICO, OTRO = "beneficiarios", "productivo", "fisico", "otro"
    CATEGORIAS = [
        (BENEFICIARIOS, "Beneficiarios"),
        (PRODUCTIVO, "Productivo (producción, rendimiento)"),
        (FISICO, "Físico (área, longitud, volumen)"),
        (OTRO, "Otro"),
    ]

    unidad_medida = models.CharField(max_length=40, help_text="Ej.: familias, personas, ha, t/año, l/s.")
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default=OTRO)

    class Meta(Catalogo.Meta):
        verbose_name = "indicador"
        verbose_name_plural = "indicadores"

    def __str__(self):
        return f"{self.nombre} ({self.unidad_medida})"


class Desagregacion(Catalogo):
    """Para separar un indicador: Hombres, Mujeres…"""

    class Meta(Catalogo.Meta):
        verbose_name = "desagregación"
        verbose_name_plural = "desagregaciones"


class Material(Catalogo):
    unidad_medida = models.CharField(max_length=40, help_text="Ej.: bolsas, barras, m².")

    class Meta(Catalogo.Meta):
        verbose_name = "material"
        verbose_name_plural = "materiales"

    def __str__(self):
        return f"{self.nombre} ({self.unidad_medida})"


class Proposito(Catalogo):
    """Forestación: propósito de la plantación."""

    class Meta(Catalogo.Meta):
        verbose_name = "propósito de forestación"
        verbose_name_plural = "propósitos de forestación"


class TipoPlanta(Catalogo):
    class Meta(Catalogo.Meta):
        verbose_name = "tipo de planta"
        verbose_name_plural = "tipos de planta"


# ---------------------------------------------------------------- proyecto


class ProyectoQuerySet(models.QuerySet):
    def vigentes(self):
        return self.filter(eliminado=False)


class Proyecto(models.Model):
    codigo = models.CharField(max_length=20, unique=True, editable=False,
                              help_text="Código legible generado por el sistema, ej. RIE-2026-0001.")
    unidad = models.ForeignKey(Unidad, on_delete=models.PROTECT, related_name="proyectos")
    programa = models.ForeignKey(Programa, on_delete=models.PROTECT, null=True, blank=True, related_name="proyectos")
    tipo = models.ForeignKey(TipoProyecto, on_delete=models.PROTECT, null=True, blank=True, related_name="proyectos")
    estado = models.ForeignKey(EstadoProyecto, on_delete=models.PROTECT, null=True, blank=True, related_name="proyectos",
                               editable=False, help_text="Lo actualiza la bitácora (Evento con estado nuevo).")
    entidad_ejecutora = models.ForeignKey(Entidad, on_delete=models.PROTECT, null=True, blank=True,
                                          related_name="proyectos_ejecutados")
    municipios = models.ManyToManyField(
        Municipio, blank=True, related_name="proyectos",
        help_text="Si se deja vacío, se completa con los municipios que tocan sus geometrías.",
    )

    nombre = models.CharField(max_length=300)
    sisin = models.CharField("SISIN", max_length=30, blank=True, help_text="Código del sistema nacional de inversión pública.")
    comunidad = models.CharField(max_length=200, blank=True)
    gestion = models.PositiveSmallIntegerField("gestión", null=True, blank=True,
                                               validators=[MinValueValidator(1990), MaxValueValidator(2100)])
    fecha_orden_proceder = models.DateField("orden de proceder", null=True, blank=True)
    fecha_conclusion = models.DateField("fecha de conclusión", null=True, blank=True)
    observaciones = models.TextField(blank=True)

    eliminado = models.BooleanField(default=False, help_text="Borrado lógico.")
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   editable=False, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    history = HistoricalRecords(m2m_fields=[municipios])
    objects = ProyectoQuerySet.as_manager()

    class Meta:
        verbose_name = "proyecto"
        verbose_name_plural = "proyectos"
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.codigo} – {self.nombre}" if self.codigo else self.nombre

    def clean(self):
        errores = {}
        for campo in ("programa", "tipo"):
            valor = getattr(self, campo)
            if valor and self.unidad_id and valor.unidad_id != self.unidad_id:
                errores[campo] = f"Pertenece a otra unidad ({valor.unidad})."
        if self.fecha_orden_proceder and self.fecha_conclusion and self.fecha_conclusion < self.fecha_orden_proceder:
            errores["fecha_conclusion"] = "No puede ser anterior a la orden de proceder."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.codigo:
            # El código usa el id, así nunca se repite aunque se guarden dos a la vez.
            prefijo = (self.unidad.clave.replace(" ", "")[:3] or "PRY").upper()
            anio = self.gestion or self.creado_en.year
            self.codigo = f"{prefijo}-{anio}-{self.pk:04d}"
            type(self).objects.filter(pk=self.pk).update(codigo=self.codigo)

    def actualizar_estado(self):
        """El estado es el del último evento de la bitácora que fijó uno."""
        ultimo = self.eventos.exclude(estado_nuevo=None).order_by("-fecha", "-id").first()
        nuevo = ultimo.estado_nuevo_id if ultimo else None
        if nuevo != self.estado_id:
            type(self).objects.filter(pk=self.pk).update(estado_id=nuevo)
            self.estado_id = nuevo

    # ---- valores calculados (no se guardan) ----

    @property
    def costo_total(self):
        return self.financiamientos.aggregate(t=Sum("monto_comprometido"))["t"] or CERO

    @property
    def desembolsado(self):
        return Desembolso.objects.filter(financiamiento__proyecto=self).aggregate(t=Sum("monto"))["t"] or CERO

    @property
    def saldo_por_desembolsar(self):
        return self.costo_total - self.desembolsado

    @property
    def avance_financiero(self):
        """% desembolsado sobre lo comprometido (None si no hay compromiso)."""
        total = self.costo_total
        return round(self.desembolsado * 100 / total, 2) if total else None

    @property
    def avance_fisico(self):
        ultimo = self.avances.order_by("-fecha").first()
        return ultimo.fisico_pct if ultimo else None

    @property
    def plazo_dias(self):
        if self.fecha_orden_proceder and self.fecha_conclusion:
            return (self.fecha_conclusion - self.fecha_orden_proceder).days
        return None


class Financiamiento(models.Model):
    """Monto comprometido por una entidad (Gobernación, GAM como contraparte, externo)."""

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="financiamientos")
    entidad = models.ForeignKey(Entidad, on_delete=models.PROTECT, related_name="financiamientos")
    monto_comprometido = models.DecimalField(**DINERO, validators=[MinValueValidator(CERO)])

    history = HistoricalRecords()

    class Meta:
        verbose_name = "financiamiento"
        verbose_name_plural = "financiamientos"
        constraints = [models.UniqueConstraint(fields=["proyecto", "entidad"], name="financiamiento_unico_por_entidad")]

    def __str__(self):
        return f"{self.entidad}: {self.monto_comprometido}"

    @property
    def desembolsado(self):
        return self.desembolsos.aggregate(t=Sum("monto"))["t"] or CERO


class Desembolso(models.Model):
    financiamiento = models.ForeignKey(Financiamiento, on_delete=models.CASCADE, related_name="desembolsos")
    fecha = models.DateField()
    monto = models.DecimalField(**DINERO, validators=[MinValueValidator(Decimal("0.01"))])
    comprobante = models.CharField(max_length=60, blank=True)
    descripcion = models.CharField("descripción", max_length=300, blank=True)
    excede_confirmado = models.BooleanField(
        "confirmo que excede lo comprometido", default=False,
        help_text="Solo si este pago hace que lo desembolsado supere lo comprometido por la entidad.",
    )
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                       editable=False, related_name="+")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "desembolso"
        verbose_name_plural = "desembolsos"
        ordering = ["fecha"]

    def __str__(self):
        return f"{self.fecha}: {self.monto}"

    def clean(self):
        if not self.financiamiento_id or self.monto is None:
            return
        otros = self.financiamiento.desembolsos.exclude(pk=self.pk).aggregate(t=Sum("monto"))["t"] or CERO
        if otros + self.monto > self.financiamiento.monto_comprometido and not self.excede_confirmado:
            raise ValidationError({"monto": (
                f"Con este pago lo desembolsado ({otros + self.monto}) supera lo comprometido por "
                f"{self.financiamiento.entidad} ({self.financiamiento.monto_comprometido}). "
                "Si es correcto, marque «confirmo que excede lo comprometido»."
            )})


class Avance(models.Model):
    """Avance físico registrado en una fecha (el financiero se calcula con los desembolsos)."""

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="avances")
    fecha = models.DateField()
    fisico_pct = models.DecimalField("avance físico (%)", max_digits=5, decimal_places=2,
                                     validators=[MinValueValidator(CERO), MaxValueValidator(Decimal("100"))])
    observacion = models.CharField("observación", max_length=300, blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "avance"
        verbose_name_plural = "avances"
        ordering = ["fecha"]
        constraints = [models.UniqueConstraint(fields=["proyecto", "fecha"], name="avance_unico_por_fecha")]

    def __str__(self):
        return f"{self.fecha}: {self.fisico_pct}%"


class ProyectoMaterial(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="materiales")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="+")
    cantidad = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(CERO)])

    class Meta:
        verbose_name = "material"
        verbose_name_plural = "materiales"
        constraints = [models.UniqueConstraint(fields=["proyecto", "material"], name="material_unico_por_proyecto")]

    def __str__(self):
        return f"{self.material}: {self.cantidad}"


class Medicion(models.Model):
    """Valor de un indicador: línea base (antes), meta, o seguimiento (después)."""

    LINEA_BASE, META, SEGUIMIENTO = "linea_base", "meta", "seguimiento"
    MOMENTOS = [(LINEA_BASE, "Línea base (antes)"), (META, "Meta"), (SEGUIMIENTO, "Seguimiento (después)")]

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="mediciones")
    indicador = models.ForeignKey(Indicador, on_delete=models.PROTECT, related_name="mediciones")
    desagregacion = models.ForeignKey(Desagregacion, on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="+", verbose_name="desagregación")
    momento = models.CharField(max_length=12, choices=MOMENTOS)
    fecha = models.DateField()
    valor = models.DecimalField(max_digits=16, decimal_places=2)
    fuente = models.CharField(max_length=200, blank=True, help_text="De dónde sale el dato (encuesta, informe…).")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                       editable=False, related_name="+")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "medición"
        verbose_name_plural = "mediciones"
        ordering = ["indicador", "fecha"]

    def __str__(self):
        extra = f" – {self.desagregacion}" if self.desagregacion_id else ""
        return f"{self.indicador}{extra}: {self.valor} ({self.get_momento_display()})"


class Geometria(models.Model):
    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="geometrias")
    tipo_elemento = models.ForeignKey(TipoElemento, on_delete=models.PROTECT, related_name="geometrias")
    nombre = models.CharField(max_length=150, blank=True)
    geom = models.GeometryField(srid=4326)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "geometría"
        verbose_name_plural = "geometrías"

    def __str__(self):
        return self.nombre or str(self.tipo_elemento)

    def clean(self):
        if not self.geom or not self.tipo_elemento_id:
            return
        esperado = self.tipo_elemento.tipo_geometria
        if self.geom.geom_type != esperado:
            raise ValidationError({"geom": f"«{self.tipo_elemento.nombre}» se dibuja como {self.tipo_elemento.get_tipo_geometria_display().lower()}."})
        try:
            proyecto = self.proyecto  # puede no estar guardado aún (alta junto con el proyecto)
        except ObjectDoesNotExist:
            proyecto = None
        if proyecto and proyecto.unidad_id and self.tipo_elemento.unidad_id != proyecto.unidad_id:
            raise ValidationError({"tipo_elemento": "Es un tipo de elemento de otra unidad."})
        if not self.geom.valid:
            raise ValidationError({"geom": f"Geometría inválida: {self.geom.valid_reason}"})
        from territorio.servicios import departamento

        limite = departamento()
        if limite is not None and not limite.intersects(self.geom):
            raise ValidationError({"geom": "Queda fuera del departamento de Cochabamba."})

    def municipios_que_toca(self):
        return Municipio.objects.filter(geom__intersects=self.geom)


class Evento(models.Model):
    """Bitácora: qué ocurrió y, si corresponde, el nuevo estado del proyecto."""

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="eventos")
    tipo = models.ForeignKey(TipoEvento, on_delete=models.PROTECT, related_name="+")
    fecha = models.DateField()
    descripcion = models.TextField("descripción")
    estado_nuevo = models.ForeignKey(EstadoProyecto, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                     help_text="Si este evento cambia el estado del proyecto.")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                editable=False, related_name="+")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "evento de bitácora"
        verbose_name_plural = "bitácora"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.fecha} – {self.tipo}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.proyecto.actualizar_estado()


@receiver(post_delete, sender=Evento)
def _evento_borrado(sender, instance, **kwargs):
    proyecto = Proyecto.objects.filter(pk=instance.proyecto_id).first()
    if proyecto:
        proyecto.actualizar_estado()


def _ruta_documento(instance, archivo):
    return f"proyectos/{instance.proyecto.codigo or instance.proyecto_id}/{archivo}"


class Documento(models.Model):
    """Opcional (D13). Solo consulta y descarga en la página del proyecto (D20)."""

    proyecto = models.ForeignKey(Proyecto, on_delete=models.CASCADE, related_name="documentos")
    tipo = models.ForeignKey(TipoDocumento, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    nombre = models.CharField(max_length=200, blank=True)
    archivo = models.FileField(upload_to=_ruta_documento)
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   editable=False, related_name="+")
    subido_en = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "documento"
        verbose_name_plural = "documentos"
        ordering = ["-subido_en"]

    def __str__(self):
        return self.nombre or self.archivo.name.rsplit("/", 1)[-1]


# ---------------------------------------------------------------- detalle por unidad (1:1)


class DetalleResiduos(models.Model):
    proyecto = models.OneToOneField(Proyecto, on_delete=models.CASCADE, related_name="detalle_residuos")
    botadero = models.CharField(max_length=200, blank=True)
    licencia = models.CharField(max_length=100, blank=True)
    riesgo = models.CharField(max_length=100, blank=True)
    ton_urbano = models.DecimalField("toneladas urbano", max_digits=12, decimal_places=2, null=True, blank=True)
    ton_rural = models.DecimalField("toneladas rural", max_digits=12, decimal_places=2, null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = "detalle de residuos sólidos"
        verbose_name_plural = "detalle de residuos sólidos"

    @property
    def ton_total(self):
        return (self.ton_urbano or CERO) + (self.ton_rural or CERO)


class DetalleForestacion(models.Model):
    proyecto = models.OneToOneField(Proyecto, on_delete=models.CASCADE, related_name="detalle_forestacion")
    proposito = models.ForeignKey(Proposito, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    campania = models.CharField("campaña", max_length=30, blank=True)
    plantines = models.PositiveIntegerField(null=True, blank=True)
    tipo_planta = models.ForeignKey(TipoPlanta, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    history = HistoricalRecords()

    class Meta:
        verbose_name = "detalle de forestación"
        verbose_name_plural = "detalle de forestación"
