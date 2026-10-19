"""
Carga inicial de regiones, provincias y municipios desde
territorio/datos/municipios.geojson (generado por herramientas/preparar_municipios.py).

En el VPS lo ejecuta el entrypoint con --si-vacio (solo la primera vez).
Las actualizaciones posteriores de límites se harán desde el importador de la app.
"""

import json
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from territorio.models import Municipio, Provincia, Region
from territorio.servicios import recalcular_agregados

ARCHIVO = Path(__file__).resolve().parents[2] / "datos" / "municipios.geojson"


class Command(BaseCommand):
    help = "Carga o actualiza regiones, provincias y municipios desde el GeoJSON de límites."

    def add_arguments(self, parser):
        parser.add_argument("--archivo", default=str(ARCHIVO))
        parser.add_argument("--si-vacio", action="store_true", help="No hace nada si ya hay municipios cargados.")

    @transaction.atomic
    def handle(self, *args, **opciones):
        if opciones["si_vacio"] and Municipio.objects.exists():
            self.stdout.write("Límites ya cargados, no se hace nada.")
            return

        with open(opciones["archivo"], encoding="utf-8") as f:
            features = json.load(f)["features"]

        codigos_provincia = {}
        for feature in features:
            p = feature["properties"]
            anterior = codigos_provincia.setdefault(p["provincia"], p["codigo_provincia"])
            if anterior != p["codigo_provincia"]:
                raise CommandError(f"Provincia {p['provincia']} con dos códigos: {anterior} y {p['codigo_provincia']}")

        provincias = {}
        for nombre, codigo in codigos_provincia.items():
            provincias[nombre], _ = Provincia.objects.update_or_create(codigo=codigo, defaults={"nombre": nombre})

        regiones = {}
        for nombre in {f["properties"]["region"] for f in features}:
            regiones[nombre], _ = Region.objects.get_or_create(nombre=nombre)

        for feature in features:
            p = feature["properties"]
            geom = GEOSGeometry(json.dumps(feature["geometry"]), srid=4326)
            if geom.geom_type == "Polygon":
                geom = MultiPolygon(geom, srid=4326)
            Municipio.objects.update_or_create(
                nombre=p["nombre"],
                defaults={
                    "codigo_ine": p["codigo_ine"],
                    "es_tioc": p["es_tioc"],
                    "provincia": provincias[p["provincia"]],
                    "region": regiones[p["region"]],
                    "geom": geom,
                },
            )

        recalcular_agregados()
        self.stdout.write(self.style.SUCCESS(
            f"{Municipio.objects.count()} municipios, {Provincia.objects.count()} provincias, "
            f"{Region.objects.count()} regiones."
        ))
