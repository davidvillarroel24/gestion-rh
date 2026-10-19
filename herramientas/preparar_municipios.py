"""
Genera src/territorio/datos/municipios.geojson a partir de los shapefiles
originales (carpeta planos/Municipios, un .shp por municipio).

Se corre una sola vez en la PC (no forma parte de la app ni de la imagen
Docker). Requiere: pyshp, shapely, pyproj.

    python herramientas/preparar_municipios.py "D:/Gestion SDMAyRH/planos/Municipios"

Correcciones aplicadas (ver README de diseño §4.2):
- Proyección Lambert propia -> EPSG:4326.
- DBF en Windows-1252 aunque el .cpg diga UTF-8.
- Totora pertenece a la provincia Carrasco (el shp dice "Totora").
- Raqaypampa es TIOC propia (el shp la nombra "Mizque" con el código de Mizque);
  queda sin código INE hasta tener el oficial.
- Villa Tunari: código 301003 -> 031003.
- Nombres: Shinaotha -> Shinahota, Sipesipe -> Sipe Sipe,
  "Cuchumuela (V. G.Villarroel)" -> Villa Gualberto Villarroel.
"""

import glob
import json
import os
import sys

import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import MultiPolygon, mapping, shape
from shapely.ops import transform
from shapely.validation import make_valid

SALIDA = os.path.join(os.path.dirname(__file__), "..", "src", "territorio", "datos", "municipios.geojson")

# Correcciones por archivo (nombre del .shp sin extensión).
CORRECCIONES = {
    "TOTORA": {"provincia": "Carrasco"},
    "RAQAYPAMPA": {"nombre": "Raqaypampa", "codigo_ine": None, "es_tioc": True},
    "VILLA_TUNARI": {"codigo_ine": "031003"},
    "SHINAHOTA": {"nombre": "Shinahota"},
    "SIPE_SIPE": {"nombre": "Sipe Sipe"},
    "VILLA_GUALBERTO_VILLARROEL": {"nombre": "Villa Gualberto Villarroel"},
}


def redondear(geom, decimales=6):
    return transform(lambda x, y, z=None: (round(x, decimales), round(y, decimales)), geom)


def main(carpeta):
    municipios = []
    for ruta in sorted(glob.glob(os.path.join(carpeta, "*.shp"))):
        clave = os.path.splitext(os.path.basename(ruta))[0]
        with open(ruta[:-4] + ".prj", encoding="latin-1") as f:
            origen = CRS.from_wkt(f.read())
        a_wgs84 = Transformer.from_crs(origen, "EPSG:4326", always_xy=True).transform

        lector = shapefile.Reader(ruta, encoding="cp1252")
        if len(lector) != 1:
            sys.exit(f"{clave}: se esperaba 1 polígono y tiene {len(lector)}")
        registro = lector.record(0).as_dict()

        geom = make_valid(transform(a_wgs84, shape(lector.shape(0).__geo_interface__)))
        if geom.geom_type == "Polygon":
            geom = MultiPolygon([geom])
        elif geom.geom_type != "MultiPolygon":
            # make_valid puede devolver una colección; quedarse solo con los polígonos.
            partes = [g for g in getattr(geom, "geoms", []) if g.geom_type == "Polygon"]
            geom = MultiPolygon(partes)

        datos = {
            "codigo_ine": str(registro["CODIGO"]).strip(),
            "nombre": str(registro["NOM_MUN"]).strip(),
            "provincia": str(registro["NOM_PROV"]).strip(),
            "region": str(registro["regiones"]).strip(),
            "es_tioc": False,
        }
        datos.update(CORRECCIONES.get(clave, {}))
        datos["codigo_provincia"] = datos["codigo_ine"][:4] if datos["codigo_ine"] else None

        municipios.append({"type": "Feature", "properties": datos, "geometry": mapping(redondear(geom))})

    # La provincia de Raqaypampa se toma de su código vecino (Mizque, 0313).
    for f in municipios:
        p = f["properties"]
        if p["codigo_provincia"] is None:
            p["codigo_provincia"] = next(
                o["properties"]["codigo_provincia"]
                for o in municipios
                if o["properties"]["provincia"] == p["provincia"] and o["properties"]["codigo_provincia"]
            )

    codigos = [f["properties"]["codigo_ine"] for f in municipios if f["properties"]["codigo_ine"]]
    if len(codigos) != len(set(codigos)):
        sys.exit("Hay códigos INE repetidos después de las correcciones")

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": municipios}, f, ensure_ascii=False)

    provincias = sorted({f["properties"]["provincia"] for f in municipios})
    regiones = sorted({f["properties"]["region"] for f in municipios})
    print(f"{len(municipios)} municipios, {len(provincias)} provincias, {len(regiones)} regiones")
    print("Provincias:", ", ".join(provincias))
    print("Regiones:", ", ".join(regiones))
    print("Archivo:", os.path.abspath(SALIDA), f"({os.path.getsize(SALIDA) / 1e6:.1f} MB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
