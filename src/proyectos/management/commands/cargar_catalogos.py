"""
Carga los valores iniciales de los catálogos (proyectos/datos_iniciales.py).

No duplica: si un valor ya existe (mismo nombre normalizado) lo deja como está,
así que se puede correr de nuevo. Correrlo una vez por base (PC y VPS); después
los catálogos se amplían desde la app.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Entidad, TipoEvento, TipoFuente, Unidad
from core.texto import normalizar
from proyectos import datos_iniciales as datos
from proyectos.models import (
    Desagregacion, EstadoProyecto, Indicador, Material, Programa, Proposito, TipoElemento, TipoPlanta, TipoProyecto,
)
from territorio.models import Municipio


class Command(BaseCommand):
    help = "Carga los valores iniciales de los catálogos tomados del sistema anterior."

    def crear(self, modelo, nombre, **extra):
        ambito = {campo: extra.pop(campo) for campo in modelo.campos_ambito}
        _, creado = modelo.objects.get_or_create(clave=normalizar(nombre), **ambito, defaults={"nombre": nombre, **extra})
        self.creados[modelo._meta.verbose_name_plural] = self.creados.get(modelo._meta.verbose_name_plural, 0) + creado

    @transaction.atomic
    def handle(self, *args, **opciones):
        self.creados = {}
        unidades = {u.clave: u for u in Unidad.objects.all()}
        fuentes = {f.clave: f for f in TipoFuente.objects.all()}

        for orden, nombre in enumerate(datos.ESTADOS, start=1):
            self.crear(EstadoProyecto, nombre, orden=orden, es_final=nombre in datos.ESTADOS_FINALES)

        for modelo, por_unidad in ((Programa, datos.PROGRAMAS), (TipoProyecto, datos.TIPOS_PROYECTO)):
            for clave_unidad, nombres in por_unidad.items():
                for nombre in nombres:
                    self.crear(modelo, nombre, unidad=unidades[clave_unidad])

        for clave_unidad, elementos in datos.TIPOS_ELEMENTO.items():
            for nombre, tipo in elementos:
                self.crear(TipoElemento, nombre, unidad=unidades[clave_unidad], tipo_geometria=tipo)

        for nombre, clave_fuente in datos.ENTIDADES:
            self.crear(Entidad, nombre, tipo_fuente=fuentes[clave_fuente])

        # Un gobierno municipal por municipio (contraparte municipal, D10).
        for municipio in Municipio.objects.all():
            nombre = f"GAIOC {municipio.nombre}" if municipio.es_tioc else f"GAM {municipio.nombre}"
            self.crear(Entidad, nombre, tipo_fuente=fuentes["municipio"], municipio=municipio)

        for nombre in datos.TIPOS_EVENTO:
            self.crear(TipoEvento, nombre)
        for nombre, unidad_medida in datos.MATERIALES:
            self.crear(Material, nombre, unidad_medida=unidad_medida)
        for nombre, unidad_medida, categoria in datos.INDICADORES:
            self.crear(Indicador, nombre, unidad_medida=unidad_medida, categoria=categoria)
        for modelo, nombres in ((Desagregacion, datos.DESAGREGACIONES), (Proposito, datos.PROPOSITOS),
                                (TipoPlanta, datos.TIPOS_PLANTA)):
            for nombre in nombres:
                self.crear(modelo, nombre)

        resumen = ", ".join(f"{n} {catalogo}" for catalogo, n in self.creados.items())
        self.stdout.write(self.style.SUCCESS(f"Creados: {resumen}."))
