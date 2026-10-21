import json
from datetime import date
from decimal import Decimal

from django.contrib.gis.geos import Point

from core import roles
from core.models import Usuario
from proyectos.models import Avance, Desembolso, Financiamiento, Geometria
from proyectos.tests import Base


class VisorApiTests(Base):
    def setUp(self):
        super().setUp()
        self.propio = self.proyecto(nombre="Riego Punata", municipios=[self.m1, self.m2], gestion=2026)
        self.ajeno = self.proyecto(nombre="Riego Lejano", municipios=[self.m3])
        self.g1 = Geometria.objects.create(proyecto=self.propio, tipo_elemento=self.toma, geom=Point(0.5, 0.5, srid=4326))
        self.g2 = Geometria.objects.create(proyecto=self.ajeno, tipo_elemento=self.toma, geom=Point(5.5, 0.5, srid=4326))
        self.tec = self.usuario("tec", roles.TECNICO, unidades=[self.riego])
        self.enc = self.usuario("enc", roles.ENCARGADO_MUNICIPAL, municipios=[self.m1])

    def json(self, metodo, url, datos=None):
        return getattr(self.client, metodo)(url, json.dumps(datos) if datos is not None else None,
                                            content_type="application/json")

    def test_pagina_requiere_login(self):
        self.assertEqual(self.client.get("/visor/").status_code, 302)
        self.client.force_login(self.enc)
        r = self.client.get("/visor/")
        self.assertContains(r, "visor/js/app")

    def test_config(self):
        self.client.force_login(self.enc)
        c = self.client.get("/visor/api/config/").json()
        self.assertEqual([m["nombre"] for m in c["municipios"]], ["Punata"])
        self.assertFalse(c["permisos"]["crear_geometria"])
        self.assertTrue(c["mapas_base"][0]["url"].startswith("https://tile.openstreetmap.org"))
        self.assertEqual(len(c["extension"]), 4)
        self.client.force_login(self.tec)
        c = self.client.get("/visor/api/config/").json()
        self.assertTrue(c["permisos"]["crear_geometria"])
        self.assertEqual({t["nombre"] for t in c["tipos_elemento"]}, {"Toma de agua", "Canal", "Área de riego"})

    def test_geometrias_respetan_alcance_y_filtros(self):
        self.client.force_login(self.enc)
        ids = [f["id"] for f in self.client.get("/visor/api/geometrias/").json()["features"]]
        self.assertEqual(ids, [self.g1.id])
        self.client.force_login(self.tec)
        self.assertEqual(len(self.client.get("/visor/api/geometrias/").json()["features"]), 2)
        filtrado = self.client.get("/visor/api/geometrias/", {"municipio": self.m3.id}).json()["features"]
        self.assertEqual([f["id"] for f in filtrado], [self.g2.id])
        en_caja = self.client.get("/visor/api/geometrias/", {"bbox": "0,0,1,1"}).json()["features"]
        self.assertEqual([f["id"] for f in en_caja], [self.g1.id])
        self.assertEqual(self.client.get("/visor/api/geometrias/", {"bbox": "x"}).status_code, 400)

    def test_crear_editar_y_borrar_geometria(self):
        self.client.force_login(self.tec)
        r = self.json("post", "/visor/api/geometrias/", {
            "proyecto": self.propio.id, "tipo_elemento": self.canal.id, "nombre": "Canal principal",
            "geometry": {"type": "LineString", "coordinates": [[0.2, 0.2], [1.5, 0.5]]}})
        self.assertEqual(r.status_code, 201, r.content)
        nueva = r.json()["id"]
        r = self.json("patch", f"/visor/api/geometrias/{nueva}/", {
            "geometry": {"type": "LineString", "coordinates": [[0.3, 0.3], [1.6, 0.6]]}, "nombre": "Canal 1"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Geometria.objects.get(pk=nueva).nombre, "Canal 1")
        self.assertEqual(self.json("delete", f"/visor/api/geometrias/{nueva}/").status_code, 200)
        self.assertFalse(Geometria.objects.filter(pk=nueva).exists())

    def test_validaciones_al_crear(self):
        self.client.force_login(self.tec)
        r = self.json("post", "/visor/api/geometrias/", {  # una toma es un punto, no una línea
            "proyecto": self.propio.id, "tipo_elemento": self.toma.id,
            "geometry": {"type": "LineString", "coordinates": [[0.2, 0.2], [0.4, 0.4]]}})
        self.assertEqual(r.status_code, 400)
        self.assertIn("geom", r.json()["detalle"])
        r = self.json("post", "/visor/api/geometrias/", {
            "proyecto": self.propio.id, "tipo_elemento": self.toma.id, "geometry": {"type": "Point", "coordinates": [40, 40]}})
        self.assertEqual(r.status_code, 400, "fuera del departamento")
        self.assertEqual(self.json("post", "/visor/api/geometrias/", {"proyecto": self.propio.id}).status_code, 400)

    def test_municipios_se_completan_desde_la_geometria(self):
        sin_municipio = self.proyecto(nombre="Nuevo")
        self.client.force_login(self.tec)
        self.json("post", "/visor/api/geometrias/", {
            "proyecto": sin_municipio.id, "tipo_elemento": self.canal.id,
            "geometry": {"type": "LineString", "coordinates": [[0.5, 0.5], [1.5, 0.5]]}})
        self.assertEqual(set(sin_municipio.municipios.all()), {self.m1, self.m2})

    def test_encargado_no_dibuja_ni_toca_lo_ajeno(self):
        self.client.force_login(self.enc)
        r = self.json("post", "/visor/api/geometrias/", {
            "proyecto": self.propio.id, "tipo_elemento": self.toma.id, "geometry": {"type": "Point", "coordinates": [0.5, 0.5]}})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.json("patch", f"/visor/api/geometrias/{self.g1.id}/", {"nombre": "x"}).status_code, 403)
        self.assertEqual(self.json("delete", f"/visor/api/geometrias/{self.g2.id}/").status_code, 404, "ajeno = inexistente")

    def test_tecnico_no_dibuja_en_proyecto_fuera_de_alcance(self):
        de_residuos = self.proyecto(unidad=self.residuos, municipios=[self.m1])
        self.client.force_login(self.tec)
        r = self.json("post", "/visor/api/geometrias/", {
            "proyecto": de_residuos.id, "tipo_elemento": self.toma.id, "geometry": {"type": "Point", "coordinates": [0.5, 0.5]}})
        self.assertEqual(r.status_code, 404)

    def test_tabla_con_totales_sin_duplicar(self):
        f = Financiamiento.objects.create(proyecto=self.propio, entidad=self.gadc, monto_comprometido=Decimal("1000"))
        Financiamiento.objects.create(proyecto=self.propio, entidad=self.gam, monto_comprometido=Decimal("500"))
        Desembolso.objects.create(financiamiento=f, fecha=date(2026, 2, 1), monto=Decimal("300"))
        Avance.objects.create(proyecto=self.propio, fecha=date(2026, 1, 1), fisico_pct=Decimal("10"))
        Avance.objects.create(proyecto=self.propio, fecha=date(2026, 3, 1), fisico_pct=Decimal("40"))
        self.client.force_login(self.tec)
        filas = {x["id"]: x for x in self.client.get("/visor/api/proyectos/").json()["filas"]}
        fila = filas[self.propio.id]  # proyecto en 2 municipios: el monto NO se duplica
        self.assertEqual((fila["costo_total"], fila["desembolsado"], fila["avance_financiero"], fila["avance_fisico"]),
                         (1500.0, 300.0, 20.0, 40.0))
        self.assertEqual(fila["municipios"], "Punata, Tacachi")
        self.assertEqual(filas[self.ajeno.id]["costo_total"], 0.0)
        por_municipio = self.client.get("/visor/api/proyectos/", {"municipio": self.m2.id}).json()["filas"]
        self.assertEqual([x["id"] for x in por_municipio], [self.propio.id])

    def test_ficha_del_proyecto(self):
        self.client.force_login(self.enc)
        ficha = self.client.get(f"/visor/api/proyectos/{self.propio.id}/").json()
        self.assertEqual(ficha["codigo"], self.propio.codigo)
        self.assertEqual(self.client.get(f"/visor/api/proyectos/{self.ajeno.id}/").status_code, 404)
        self.client.force_login(Usuario.objects.create_superuser("root", password="clave-de-prueba-123"))
        ficha = self.client.get(f"/visor/api/proyectos/{self.propio.id}/").json()
        self.assertIn(f"/admin/proyectos/proyecto/{self.propio.id}/change/", ficha["url_admin"])
