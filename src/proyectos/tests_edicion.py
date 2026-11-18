"""Edición del proyecto dentro del sistema (sin /admin): /proyectos/<id>/editar/ y /proyectos/nuevo/."""

from datetime import date
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from core import roles
from core.models import TipoEvento

from .models import Avance, Desembolso, Documento, EstadoProyecto, Evento, Financiamiento, Geometria, Proyecto
from .tests import MEDIA_PRUEBA, Base


def gestion(prefijo, filas, total=None, iniciales=0):
    """Datos de un formset: filas = [{campo: valor}]."""
    datos = {f"{prefijo}-TOTAL_FORMS": str(total if total is not None else len(filas)),
             f"{prefijo}-INITIAL_FORMS": str(iniciales), f"{prefijo}-MIN_NUM_FORMS": "0", f"{prefijo}-MAX_NUM_FORMS": "1000"}
    for i, fila in enumerate(filas):
        datos.update({f"{prefijo}-{i}-{k}": v for k, v in fila.items()})
    return datos


@override_settings(MEDIA_ROOT=MEDIA_PRUEBA)
class EdicionTests(Base):
    def setUp(self):
        super().setUp()
        self.p = self.proyecto(nombre="Riego Punata", municipios=[self.m1], gestion=2026)
        self.tec = self.usuario("tec", roles.TECNICO, unidades=[self.riego])
        self.client.force_login(self.tec)
        self.url = f"/proyectos/{self.p.pk}/editar/"

    def test_pagina_con_todas_las_secciones_y_modo_incrustado(self):
        r = self.client.get(self.url)
        for seccion in ("Datos generales", "Financiamiento", "Avance físico", "Materiales", "Mediciones", "Bitácora",
                        "Documentos", "Geometrías", "Historial"):
            self.assertContains(r, seccion)
        self.assertContains(r, "barra-superior")
        r = self.client.get(self.url, {"incrustado": "1", "seccion": "avances"})
        self.assertNotContains(r, "barra-superior", msg_prefix="dentro del visor no repite la barra")
        self.assertEqual(r["X-Frame-Options"], "SAMEORIGIN", "se puede mostrar dentro del visor (mismo sitio)")
        self.assertContains(r, 'href="?seccion=general&incrustado=1"', msg_prefix="las pestañas conservan el modo incrustado")

    def test_fuera_de_alcance(self):
        ajeno = self.proyecto(unidad=self.residuos, nombre="Botadero")
        self.assertEqual(self.client.get(f"/proyectos/{ajeno.pk}/editar/").status_code, 404)

    def test_guardar_datos_generales(self):
        r = self.client.post(self.url, {"unidad": self.riego.pk, "nombre": "Riego Punata II", "municipios": [self.m1.pk, self.m2.pk],
                                        "gestion": 2026, "fecha_orden_proceder": "2026-03-01", "fecha_conclusion": "2026-02-01"})
        self.assertContains(r, "No puede ser anterior a la orden de proceder", msg_prefix="misma validación que el modelo")
        r = self.client.post(self.url, {"unidad": self.riego.pk, "nombre": "Riego Punata II", "municipios": [self.m1.pk, self.m2.pk],
                                        "gestion": 2026, "fecha_orden_proceder": "2026-03-01"})
        self.assertRedirects(r, f"{self.url}?seccion=general", fetch_redirect_response=False)
        self.p.refresh_from_db()
        self.assertEqual((self.p.nombre, self.p.municipios.count(), self.p.fecha_orden_proceder), ("Riego Punata II", 2, date(2026, 3, 1)))

    def test_financiamiento_y_desembolsos(self):
        datos = gestion("financiamiento", [{"entidad": self.gadc.pk, "monto_comprometido": "1000"}], total=1)
        datos.update(gestion("desembolsos", [], total=0))
        r = self.client.post(f"{self.url}?seccion=financiamiento", datos)
        self.assertEqual(r.status_code, 302)
        f = Financiamiento.objects.get(proyecto=self.p)
        datos = gestion("financiamiento", [{"id": f.pk, "entidad": self.gadc.pk, "monto_comprometido": "1000"}], iniciales=1)
        datos.update(gestion("desembolsos", [{"financiamiento": f.pk, "fecha": "2026-04-10", "monto": "400", "comprobante": "C-1"}]))
        r = self.client.post(f"{self.url}?seccion=financiamiento", datos)
        self.assertEqual(r.status_code, 302)
        d = Desembolso.objects.get(financiamiento=f)
        self.assertEqual((d.monto, d.registrado_por), (Decimal("400"), self.tec), "el autor se completa solo")
        self.assertEqual(self.p.desembolsado, Decimal("400"))

    def test_bitacora_cambia_estado_y_borrar_fila(self):
        tipo = TipoEvento.objects.create(nombre="Cambio de estado")
        estado = EstadoProyecto.objects.create(nombre="En ejecución")
        r = self.client.post(f"{self.url}?seccion=bitacora", gestion("bitacora", [
            {"fecha": "2026-05-01", "tipo": tipo.pk, "descripcion": "Inicio de obra", "estado_nuevo": estado.pk}]))
        self.assertEqual(r.status_code, 302)
        self.p.refresh_from_db()
        self.assertEqual(self.p.estado, estado)
        Avance.objects.create(proyecto=self.p, fecha=date(2026, 5, 1), fisico_pct=10)
        a = Avance.objects.get(proyecto=self.p)
        r = self.client.post(f"{self.url}?seccion=avances", gestion("avances", [
            {"id": a.pk, "fecha": "2026-05-01", "fisico_pct": "10", "DELETE": "on"}], iniciales=1))
        self.assertFalse(Avance.objects.filter(proyecto=self.p).exists())

    def test_documento_y_geometrias(self):
        archivo = SimpleUploadedFile("acta.pdf", b"%PDF-1.4 prueba", content_type="application/pdf")
        r = self.client.post(f"{self.url}?seccion=documentos", gestion("documentos", [{"nombre": "Acta", "archivo": archivo}]))
        self.assertEqual(r.status_code, 302)
        doc = Documento.objects.get(proyecto=self.p)
        self.assertEqual(doc.subido_por, self.tec)
        self.assertContains(self.client.get(f"{self.url}?seccion=documentos"), f"/proyectos/documentos/{doc.pk}/descargar/")
        g = Geometria.objects.create(proyecto=self.p, tipo_elemento=self.toma, nombre="Toma", geom=Point(0.5, 0.5, srid=4326))
        r = self.client.get(f"{self.url}?seccion=geometrias")
        self.assertContains(r, f'data-geometria="{g.pk}"')
        self.assertNotContains(r, "Agregar fila", msg_prefix="las geometrías nuevas se dibujan en el mapa")

    def test_encargado_municipal_solo_lo_suyo(self):
        enc = self.usuario("enc", roles.ENCARGADO_MUNICIPAL, municipios=[self.m1])
        self.client.force_login(enc)
        r = self.client.get(self.url)
        self.assertContains(r, "puede ver esta sección pero no modificarla")
        self.assertEqual(self.client.post(self.url, {"nombre": "x"}).status_code, 403)
        self.assertNotContains(self.client.get(f"{self.url}?seccion=mediciones"), "no modificarla")

    def test_historial(self):
        self.client.post(self.url, {"unidad": self.riego.pk, "nombre": "Nombre nuevo", "municipios": [self.m1.pk]})
        r = self.client.get(f"{self.url}?seccion=historial")
        self.assertContains(r, "Modificado")
        self.assertContains(r, "Nombre nuevo")

    def test_nuevo_proyecto(self):
        r = self.client.post("/proyectos/nuevo/?incrustado=1", {"unidad": self.riego.pk, "nombre": "Proyecto nuevo",
                                                                "municipios": [self.m2.pk]})
        p = Proyecto.objects.get(nombre="Proyecto nuevo")
        self.assertRedirects(r, f"/proyectos/{p.pk}/editar/?incrustado=1", fetch_redirect_response=False)
        self.assertEqual(p.creado_por, self.tec)
        consulta = self.usuario("ver", roles.CONSULTA)
        self.client.force_login(consulta)
        self.assertEqual(self.client.get("/proyectos/nuevo/").status_code, 403)
