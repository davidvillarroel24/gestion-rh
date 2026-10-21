import json
import os
import shutil
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group
from django.contrib.gis.geos import LineString, MultiPolygon, Point, Polygon
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core import roles
from core.models import Entidad, TipoEvento, TipoFuente, Unidad, Usuario
from core.roles import sincronizar_roles
from territorio.models import Municipio, Provincia, Region
from territorio.servicios import recalcular_agregados

from .models import (
    Avance, Desembolso, Documento, EstadoProyecto, Evento, Financiamiento, Geometria, Medicion, Indicador,
    Proyecto, TipoElemento, TipoProyecto,
)

MEDIA_PRUEBA = tempfile.mkdtemp()


def cuadrado(x, y=0, lado=1):
    return MultiPolygon(Polygon(((x, y), (x + lado, y), (x + lado, y + lado), (x, y + lado), (x, y))), srid=4326)


@override_settings(MEDIA_ROOT=MEDIA_PRUEBA)
class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        valles = Region.objects.create(nombre="Valles")
        punata = Provincia.objects.create(codigo="0314", nombre="Punata")
        # Dos municipios vecinos: [0,1]x[0,1] y [1,2]x[0,1]
        cls.m1 = Municipio.objects.create(nombre="Punata", codigo_ine="031401", provincia=punata, region=valles, geom=cuadrado(0))
        cls.m2 = Municipio.objects.create(nombre="Tacachi", codigo_ine="031404", provincia=punata, region=valles, geom=cuadrado(1))
        cls.m3 = Municipio.objects.create(nombre="Lejano", codigo_ine="031405", provincia=punata, region=valles, geom=cuadrado(5))
        cls.riego = Unidad.objects.get_or_create(clave="riego", defaults={"nombre": "Riego"})[0]
        cls.residuos = Unidad.objects.get_or_create(clave="residuos solidos", defaults={"nombre": "Residuos Sólidos"})[0]
        gob = TipoFuente.objects.get_or_create(clave="gobernacion", defaults={"nombre": "Gobernación"})[0]
        mun = TipoFuente.objects.get_or_create(clave="municipio", defaults={"nombre": "Municipio"})[0]
        ext = TipoFuente.objects.get_or_create(clave="externo", defaults={"nombre": "Externo"})[0]
        cls.gadc = Entidad.objects.create(nombre="GADC", tipo_fuente=gob)
        cls.gam = Entidad.objects.create(nombre="GAM Punata", tipo_fuente=mun, municipio=cls.m1)
        cls.bid = Entidad.objects.create(nombre="BID", tipo_fuente=ext)
        cls.toma = TipoElemento.objects.create(nombre="Toma de agua", unidad=cls.riego, tipo_geometria=TipoElemento.PUNTO)
        cls.canal = TipoElemento.objects.create(nombre="Canal", unidad=cls.riego, tipo_geometria=TipoElemento.LINEA)
        cls.area = TipoElemento.objects.create(nombre="Área de riego", unidad=cls.riego, tipo_geometria=TipoElemento.POLIGONO)

    def setUp(self):
        cache.clear()
        recalcular_agregados()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_PRUEBA, ignore_errors=True)

    def proyecto(self, unidad=None, municipios=(), **kw):
        p = Proyecto.objects.create(unidad=unidad or self.riego, nombre=kw.pop("nombre", "Sistema de riego X"), **kw)
        p.municipios.set(municipios)
        return p

    def usuario(self, nombre, rol, unidades=(), municipios=()):
        u = Usuario.objects.create_user(nombre, password="clave-de-prueba-123", is_staff=True)
        u.groups.add(Group.objects.get(name=rol))
        u.unidades.set(unidades)
        u.municipios.set(municipios)
        return u


class ProyectoTests(Base):
    def test_codigo_legible_y_unico(self):
        p = self.proyecto(gestion=2026)
        self.assertEqual(p.codigo, f"RIE-2026-{p.pk:04d}")
        q = self.proyecto(unidad=self.residuos, gestion=2025)
        self.assertTrue(q.codigo.startswith("RES-2025-"))

    def test_dinero_por_proyecto_sin_duplicar(self):
        p = self.proyecto(municipios=[self.m1, self.m2])  # mancomunado: 2 municipios
        f1 = Financiamiento.objects.create(proyecto=p, entidad=self.gadc, monto_comprometido=Decimal("700000"))
        Financiamiento.objects.create(proyecto=p, entidad=self.gam, monto_comprometido=Decimal("100000"))
        Financiamiento.objects.create(proyecto=p, entidad=self.bid, monto_comprometido=Decimal("200000"))
        Desembolso.objects.create(financiamiento=f1, fecha=date(2026, 3, 1), monto=Decimal("250000"))
        Desembolso.objects.create(financiamiento=f1, fecha=date(2026, 6, 1), monto=Decimal("250000"))
        self.assertEqual(p.costo_total, Decimal("1000000"))
        self.assertEqual(p.desembolsado, Decimal("500000"))
        self.assertEqual(p.saldo_por_desembolsar, Decimal("500000"))
        self.assertEqual(p.avance_financiero, Decimal("50.00"))

    def test_desembolso_que_excede_pide_confirmar(self):
        f = Financiamiento.objects.create(proyecto=self.proyecto(), entidad=self.gadc, monto_comprometido=Decimal("100"))
        Desembolso.objects.create(financiamiento=f, fecha=date(2026, 1, 1), monto=Decimal("80"))
        exceso = Desembolso(financiamiento=f, fecha=date(2026, 2, 1), monto=Decimal("30"))
        with self.assertRaises(ValidationError):
            exceso.full_clean()
        exceso.excede_confirmado = True
        exceso.full_clean()

    def test_estado_lo_define_la_bitacora(self):
        p = self.proyecto()
        en_ejecucion = EstadoProyecto.objects.create(nombre="En ejecución", orden=1)
        concluido = EstadoProyecto.objects.create(nombre="Concluido", orden=2)
        observacion = TipoEvento.objects.create(nombre="Observación")
        cambio = TipoEvento.objects.create(nombre="Cambio de estado")
        Evento.objects.create(proyecto=p, tipo=cambio, fecha=date(2026, 1, 10), descripcion="Inicio", estado_nuevo=en_ejecucion)
        Evento.objects.create(proyecto=p, tipo=observacion, fecha=date(2026, 2, 1), descripcion="Lluvias")
        p.refresh_from_db()
        self.assertEqual(p.estado, en_ejecucion, "un evento sin estado no cambia el estado")
        fin = Evento.objects.create(proyecto=p, tipo=cambio, fecha=date(2026, 9, 1), descripcion="Fin", estado_nuevo=concluido)
        p.refresh_from_db()
        self.assertEqual(p.estado, concluido)
        fin.delete()
        p.refresh_from_db()
        self.assertEqual(p.estado, en_ejecucion, "al borrar el evento vuelve el estado anterior")

    def test_avance_fisico_es_el_ultimo(self):
        p = self.proyecto()
        Avance.objects.create(proyecto=p, fecha=date(2026, 5, 1), fisico_pct=Decimal("60"))
        Avance.objects.create(proyecto=p, fecha=date(2026, 3, 1), fisico_pct=Decimal("30"))
        self.assertEqual(p.avance_fisico, Decimal("60"))

    def test_programa_o_tipo_de_otra_unidad(self):
        tipo = TipoProyecto.objects.create(nombre="Construcción", unidad=self.residuos)
        p = Proyecto(unidad=self.riego, nombre="X", tipo=tipo)
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_mismo_nombre_en_dos_unidades(self):
        TipoProyecto.objects.create(nombre="Construcción", unidad=self.riego)
        TipoProyecto(nombre="Construcción", unidad=self.residuos).full_clean()  # permitido
        with self.assertRaises(ValidationError):
            TipoProyecto(nombre="CONSTRUCCION", unidad=self.riego).full_clean()


class GeometriaTests(Base):
    def test_varias_geometrias_con_su_tipo(self):
        p = self.proyecto()
        for tipo, geom in [(self.toma, Point(0.5, 0.5, srid=4326)),
                           (self.canal, LineString((0.5, 0.5), (1.5, 0.5), srid=4326)),
                           (self.area, Polygon(((1.2, 0.2), (1.8, 0.2), (1.8, 0.8), (1.2, 0.2)), srid=4326))]:
            g = Geometria(proyecto=p, tipo_elemento=tipo, geom=geom)
            g.full_clean()
            g.save()
        self.assertEqual(p.geometrias.count(), 3)
        canal = p.geometrias.get(tipo_elemento=self.canal)
        self.assertEqual(set(canal.municipios_que_toca()), {self.m1, self.m2})

    def test_tipo_de_geometria_incorrecto(self):
        g = Geometria(proyecto=self.proyecto(), tipo_elemento=self.toma,
                      geom=LineString((0.1, 0.1), (0.2, 0.2), srid=4326))
        with self.assertRaisesMessage(ValidationError, "punto"):
            g.full_clean()

    def test_fuera_del_departamento(self):
        g = Geometria(proyecto=self.proyecto(), tipo_elemento=self.toma, geom=Point(30, 30, srid=4326))
        with self.assertRaisesMessage(ValidationError, "fuera del departamento"):
            g.full_clean()

    def test_tipo_de_elemento_de_otra_unidad(self):
        otro = TipoElemento.objects.create(nombre="Botadero", unidad=self.residuos, tipo_geometria=TipoElemento.PUNTO)
        g = Geometria(proyecto=self.proyecto(), tipo_elemento=otro, geom=Point(0.5, 0.5, srid=4326))
        with self.assertRaises(ValidationError):
            g.full_clean()


class PermisosYAlcanceTests(Base):
    def test_permisos_por_rol(self):
        tec = self.usuario("tec", roles.TECNICO, unidades=[self.riego])
        enc = self.usuario("enc", roles.ENCARGADO_MUNICIPAL, municipios=[self.m1])
        self.assertTrue(tec.has_perm("proyectos.change_proyecto"))
        self.assertFalse(tec.has_perm("proyectos.delete_proyecto"), "el proyecto tiene borrado lógico")
        self.assertTrue(tec.has_perm("proyectos.delete_avance"))
        self.assertTrue(enc.has_perm("proyectos.add_medicion"))
        self.assertTrue(enc.has_perm("proyectos.add_evento"))
        self.assertFalse(enc.has_perm("proyectos.change_proyecto"))
        self.assertFalse(enc.has_perm("proyectos.add_financiamiento"))
        self.assertFalse(enc.has_perm("proyectos.add_indicador"))

    def test_listados_respetan_el_alcance(self):
        del_m1 = self.proyecto(nombre="En Punata", municipios=[self.m1])
        del_m3 = self.proyecto(nombre="En Lejano", municipios=[self.m3])
        de_residuos = self.proyecto(unidad=self.residuos, nombre="Botadero", municipios=[self.m1])

        self.client.force_login(self.usuario("enc", roles.ENCARGADO_MUNICIPAL, municipios=[self.m1]))
        contenido = self.client.get("/admin/proyectos/proyecto/").content.decode()
        self.assertIn(del_m1.codigo, contenido)
        self.assertIn(de_residuos.codigo, contenido)
        self.assertNotIn(del_m3.codigo, contenido)
        self.assertEqual(self.client.get(f"/admin/proyectos/proyecto/{del_m3.pk}/change/").status_code, 302,
                         "fuera de su alcance: el admin lo trata como inexistente")

        self.client.force_login(self.usuario("tec", roles.TECNICO, unidades=[self.riego]))
        contenido = self.client.get("/admin/proyectos/proyecto/").content.decode()
        self.assertIn(del_m3.codigo, contenido)
        self.assertNotIn(de_residuos.codigo, contenido)

    def test_encargado_solo_carga_mediciones_de_su_municipio(self):
        propio = self.proyecto(municipios=[self.m1])
        ajeno = self.proyecto(municipios=[self.m3])
        familias = Indicador.objects.create(nombre="Familias beneficiadas", unidad_medida="familias")
        self.client.force_login(self.usuario("enc", roles.ENCARGADO_MUNICIPAL, municipios=[self.m1]))
        datos = {"indicador": familias.pk, "momento": Medicion.SEGUIMIENTO, "fecha": "2026-10-01", "valor": "45"}
        r = self.client.post("/admin/proyectos/medicion/add/", {**datos, "proyecto": ajeno.pk})
        self.assertEqual(r.status_code, 200, "debe rechazar el proyecto ajeno")
        self.assertFalse(Medicion.objects.exists())
        r = self.client.post("/admin/proyectos/medicion/add/", {**datos, "proyecto": propio.pk})
        self.assertEqual(r.status_code, 302)
        medicion = Medicion.objects.get()
        self.assertEqual(medicion.registrado_por.username, "enc")

    def test_paginas_del_proyecto_abren(self):
        p = self.proyecto(municipios=[self.m1])
        Geometria.objects.create(proyecto=p, tipo_elemento=self.toma, geom=Point(0.5, 0.5, srid=4326))
        self.client.force_login(Usuario.objects.create_superuser("root", password="clave-de-prueba-123"))
        for url in (f"/admin/proyectos/proyecto/{p.pk}/change/", "/admin/proyectos/proyecto/add/",
                    "/admin/proyectos/financiamiento/add/", f"/admin/proyectos/proyecto/{p.pk}/history/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)


class DocumentoTests(Base):
    def test_descarga_respeta_alcance(self):
        propio = self.proyecto(municipios=[self.m1])
        ajeno = self.proyecto(municipios=[self.m3])
        d1 = Documento.objects.create(proyecto=propio, archivo=SimpleUploadedFile("acta.pdf", b"%PDF-1"))
        d2 = Documento.objects.create(proyecto=ajeno, archivo=SimpleUploadedFile("otro.pdf", b"%PDF-2"))

        self.assertEqual(self.client.get(f"/proyectos/documentos/{d1.pk}/descargar/").status_code, 302, "pide login")
        self.client.force_login(self.usuario("enc", roles.ENCARGADO_MUNICIPAL, municipios=[self.m1]))
        r = self.client.get(f"/proyectos/documentos/{d1.pk}/descargar/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), b"%PDF-1")
        self.assertEqual(self.client.get(f"/proyectos/documentos/{d2.pk}/descargar/").status_code, 404)
        self.assertEqual(self.client.get(f"/media/{d1.archivo.name}").status_code, 200)
        self.assertEqual(self.client.get(f"/media/{d2.archivo.name}").status_code, 404, "media no es público")


class CargarCatalogosTests(Base):
    def test_carga_y_no_duplica(self):
        from django.core.management import call_command

        call_command("cargar_catalogos", stdout=open(os.devnull, "w"))
        cantidades = (EstadoProyecto.objects.count(), TipoElemento.objects.count(), Entidad.objects.count())
        call_command("cargar_catalogos", stdout=open(os.devnull, "w"))
        self.assertEqual((EstadoProyecto.objects.count(), TipoElemento.objects.count(), Entidad.objects.count()), cantidades)
        self.assertTrue(Entidad.objects.filter(nombre="GAM Punata", municipio=self.m1).exists(),
                        "un gobierno municipal por municipio")


class CatalogoPorUnidadApiTests(Base):
    def test_requiere_unidad_y_la_respeta(self):
        self.client.force_login(self.usuario("tec", roles.TECNICO, unidades=[self.riego]))
        url = "/catalogos/tipos-proyecto/"
        self.assertEqual(self.client.get(url).status_code, 400)
        r = self.client.post(url, json.dumps({"nombre": "Mejoramiento", "unidad": self.riego.pk}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 201)
        r = self.client.post(url, json.dumps({"nombre": "Mejoramiento", "unidad": self.residuos.pk}),
                             content_type="application/json")
        self.assertEqual(r.status_code, 403, "unidad fuera de su alcance")
        self.assertEqual(self.client.get(url, {"unidad": self.riego.pk}).json()[0]["nombre"], "Mejoramiento")
