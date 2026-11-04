import json

from django.contrib.auth.models import Group
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.exceptions import ValidationError
from django.forms import modelform_factory
from django.test import TestCase

from territorio.models import Municipio, Provincia, Region

from . import alcance, roles
from .admin import CatalogoForm
from .models import TipoEvento, Unidad, Usuario
from .roles import sincronizar_roles
from .texto import normalizar, similitud


def cuadrado(x):
    return MultiPolygon(Polygon(((x, 0), (x + 1, 0), (x + 1, 1), (x, 1), (x, 0))), srid=4326)


class TextoTests(TestCase):
    def test_normalizar(self):
        self.assertEqual(normalizar("  Gestión   de RIESGOS. "), "gestion de riesgos")

    def test_similitud(self):
        self.assertEqual(similitud("observacion", "observacion"), 1.0)
        self.assertGreaterEqual(similitud("paralizacion", "paralizacion temporal"), 0.8)
        self.assertLess(similitud("riego", "residuos solidos"), 0.8)


class CatalogoTests(TestCase):
    def test_no_permite_duplicado_normalizado(self):
        TipoEvento.objects.create(nombre="Observación")
        with self.assertRaises(ValidationError):
            TipoEvento(nombre="OBSERVACION ").full_clean()

    def test_parecidos(self):
        TipoEvento.objects.create(nombre="Paralización")
        self.assertEqual([p.nombre for p in TipoEvento.parecidos("Paralizacion temporal")], ["Paralización"])

    def test_formulario_admin_pide_confirmar_parecido(self):
        # El admin arma el formulario así (modelform_factory con CatalogoForm como base).
        Form = modelform_factory(TipoEvento, form=CatalogoForm, fields=["nombre", "activo"])
        TipoEvento.objects.create(nombre="Paralización")
        form = Form(data={"nombre": "Paralizacion temporal", "activo": True})
        self.assertFalse(form.is_valid())
        self.assertIn("Se parece a", str(form.errors))
        form = Form(data={"nombre": "Paralizacion temporal", "activo": True, "confirmar_parecido": True})
        self.assertTrue(form.is_valid(), form.errors)
        form = Form(data={"nombre": "PARALIZACIÓN", "activo": True, "confirmar_parecido": True})
        self.assertFalse(form.is_valid(), "un duplicado exacto no se acepta ni confirmando")


class BaseRolesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()
        region = Region.objects.create(nombre="Valles")
        provincia = Provincia.objects.create(codigo="0314", nombre="Punata")
        cls.punata = Municipio.objects.create(nombre="Punata", codigo_ine="031401", provincia=provincia,
                                              region=region, geom=cuadrado(0))
        cls.tacachi = Municipio.objects.create(nombre="Tacachi", codigo_ine="031404", provincia=provincia,
                                               region=region, geom=cuadrado(2))
        cls.riego = Unidad.objects.get_or_create(clave="riego", defaults={"nombre": "Riego"})[0]
        cls.residuos = Unidad.objects.get_or_create(clave="residuos solidos", defaults={"nombre": "Residuos Sólidos"})[0]

    def crear(self, username, rol=None, unidades=(), municipios=()):
        u = Usuario.objects.create_user(username, password="clave-de-prueba-123")
        if rol:
            u.groups.add(Group.objects.get(name=rol))
        u.unidades.set(unidades)
        u.municipios.set(municipios)
        return Usuario.objects.get(pk=u.pk)


class RolesTests(BaseRolesTests):
    def test_existen_los_cinco_roles(self):
        self.assertEqual(set(Group.objects.values_list("name", flat=True)), set(roles.ROLES))

    def test_permisos(self):
        tecnico = self.crear("tec", roles.TECNICO)
        consulta = self.crear("con", roles.CONSULTA)
        encargado = self.crear("enc", roles.ENCARGADO_MUNICIPAL)
        self.assertTrue(tecnico.has_perm("core.add_tipoevento"))
        self.assertFalse(tecnico.has_perm("core.add_unidad"))
        self.assertTrue(consulta.has_perm("territorio.view_municipio"))
        self.assertFalse(consulta.has_perm("core.change_tipoevento"))
        self.assertFalse(encargado.has_perm("core.view_usuario"), "los usuarios no entran por el comodín core.*")
        self.assertTrue(self.crear("adm", roles.ADMINISTRADOR).has_perm("core.change_usuario"))


class AlcanceTests(BaseRolesTests):
    def test_encargado_solo_ve_su_municipio(self):
        enc = self.crear("enc", roles.ENCARGADO_MUNICIPAL, municipios=[self.punata])
        self.assertEqual(list(alcance.municipios_visibles(enc)), [self.punata])
        qs = alcance.filtrar(Municipio.objects.all(), enc, campo_municipio="pk")
        self.assertEqual(list(qs), [self.punata])

    def test_tecnico_solo_ve_su_unidad(self):
        tec = self.crear("tec", roles.TECNICO, unidades=[self.riego])
        self.assertEqual(list(alcance.unidades_visibles(tec)), [self.riego])
        self.assertEqual(list(alcance.filtrar(Unidad.objects.all(), tec, campo_unidad="pk")), [self.riego])
        self.assertEqual(alcance.municipios_visibles(tec).count(), 2)

    def test_consulta_ve_todo_y_sin_rol_nada(self):
        self.assertEqual(alcance.filtrar(Municipio.objects.all(), self.crear("con", roles.CONSULTA)).count(), 2)
        self.assertEqual(alcance.filtrar(Municipio.objects.all(), self.crear("nadie"), campo_municipio="pk").count(), 0)

    def test_roles_combinados_suman_alcance(self):
        u = self.crear("ambos", roles.TECNICO, unidades=[self.riego], municipios=[self.tacachi])
        u.groups.add(Group.objects.get(name=roles.ENCARGADO_MUNICIPAL))
        u = Usuario.objects.get(pk=u.pk)
        self.assertEqual(alcance.filtrar(Unidad.objects.all(), u, campo_unidad="pk").count(), 1)
        self.assertEqual(alcance.filtrar(Municipio.objects.all(), u, campo_municipio="pk").count(), 1)


class CatalogoApiTests(BaseRolesTests):
    url = "/catalogos/tipos-evento/"

    def post(self, **datos):
        return self.client.post(self.url, json.dumps(datos), content_type="application/json")

    def test_requiere_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_crear_existente_parecido_y_confirmar(self):
        self.client.force_login(self.crear("tec", roles.TECNICO))
        r = self.post(nombre="Paralización")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.post(nombre=" PARALIZACION ").json()["existente"], True)
        r = self.post(nombre="Paralizacion temporal")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["parecidos"][0]["nombre"], "Paralización")
        self.assertEqual(self.post(nombre="Paralizacion temporal", confirmar=1).status_code, 201)
        self.assertEqual(TipoEvento.objects.count(), 2)

    def test_buscar(self):
        TipoEvento.objects.create(nombre="Ampliación de plazo")
        self.client.force_login(self.crear("con", roles.CONSULTA))
        self.assertEqual(self.client.get(self.url, {"q": "AMPLIACION"}).json()[0]["nombre"], "Ampliación de plazo")

    def test_sin_permiso_para_crear(self):
        self.client.force_login(self.crear("con", roles.CONSULTA))
        self.assertEqual(self.post(nombre="Visita").status_code, 403)
        self.client.force_login(self.crear("tec", roles.TECNICO))
        r = self.client.post("/catalogos/unidades/", json.dumps({"nombre": "Nueva"}), content_type="application/json")
        self.assertEqual(r.status_code, 403, "solo el administrador crea unidades")

    def test_catalogo_inexistente(self):
        self.client.force_login(self.crear("adm", roles.ADMINISTRADOR))
        self.assertEqual(self.client.get("/catalogos/nada/").status_code, 404)


class AdminTests(BaseRolesTests):
    def test_paginas_del_admin_abren(self):
        from django.contrib import admin

        self.client.force_login(Usuario.objects.create_superuser("root", password="clave-de-prueba-123"))
        for modelo in admin.site._registry:
            info = (modelo._meta.app_label, modelo._meta.model_name)
            for url in (f"/admin/{info[0]}/{info[1]}/", f"/admin/{info[0]}/{info[1]}/add/"):
                self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get(f"/admin/territorio/municipio/{self.punata.pk}/change/").status_code, 200)
        self.assertEqual(self.client.get(f"/admin/territorio/municipio/{self.punata.pk}/history/").status_code, 200)


class InicioTests(BaseRolesTests):
    def test_redirige_al_login(self):
        r = self.client.get("/")
        self.assertRedirects(r, "/ingresar/?next=/", fetch_redirect_response=False)

    def test_despues_del_login_va_a_su_pagina_principal(self):
        self.crear("enc", roles.ENCARGADO_MUNICIPAL, municipios=[self.tacachi])
        r = self.client.post("/ingresar/", {"username": "enc", "password": "clave-de-prueba-123"})
        self.assertRedirects(r, "/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/"), "/visor/", fetch_redirect_response=False)


class UsuariosTests(BaseRolesTests):
    def setUp(self):
        self.admin = self.crear("jefa", roles.ADMINISTRADOR)
        self.client.force_login(self.admin)
        self.tecnico = Group.objects.get(name=roles.TECNICO)

    def datos(self, **cambios):
        return {"first_name": "Ana", "last_name": "Rojas", "username": "arojas", "email": "", "is_active": "on",
                "rol": self.tecnico.pk, "unidades": [self.riego.pk], "contrasena": "Riego-2026-segura",
                "contrasena2": "Riego-2026-segura", **cambios}

    def test_solo_el_administrador(self):
        self.client.force_login(self.crear("tec", roles.TECNICO, unidades=[self.riego]))
        self.assertEqual(self.client.get("/usuarios/").status_code, 403)
        self.assertEqual(self.client.post("/usuarios/nuevo/", self.datos()).status_code, 403)
        self.assertNotContains(self.client.get("/importar/"), 'href="/usuarios/"')

    def test_crear_tecnico_con_su_area(self):
        self.assertContains(self.client.get("/importar/"), 'href="/usuarios/"', msg_prefix="enlace solo para el admin")
        r = self.client.post("/usuarios/nuevo/", self.datos())
        self.assertRedirects(r, "/usuarios/", fetch_redirect_response=False)
        u = Usuario.objects.get(username="arojas")
        self.assertEqual([g.name for g in u.groups.all()], [roles.TECNICO])
        self.assertEqual(list(u.unidades.all()), [self.riego])
        self.assertTrue(u.is_staff, "edita sus proyectos en la administración")
        self.assertTrue(u.check_password("Riego-2026-segura"))
        self.assertContains(self.client.get("/usuarios/", {"q": "rojas"}), "arojas")

    def test_validaciones(self):
        r = self.client.post("/usuarios/nuevo/", self.datos(unidades=[], contrasena2="otra"))
        self.assertContains(r, "necesita al menos un área")
        self.assertContains(r, "no coinciden")
        encargado = Group.objects.get(name=roles.ENCARGADO_MUNICIPAL)
        self.assertContains(self.client.post("/usuarios/nuevo/", self.datos(rol=encargado.pk)), "al menos un municipio")
        self.assertFalse(Usuario.objects.filter(username="arojas").exists())

    def test_editar_cambia_rol_y_no_toca_la_contrasena(self):
        u = self.crear("ana", roles.TECNICO, unidades=[self.riego])
        consulta = Group.objects.get(name=roles.CONSULTA)
        r = self.client.post(f"/usuarios/{u.pk}/", self.datos(username="ana", rol=consulta.pk, unidades=[],
                                                             contrasena="", contrasena2="", is_active=""))
        self.assertRedirects(r, "/usuarios/", fetch_redirect_response=False)
        u.refresh_from_db()
        self.assertEqual([g.name for g in u.groups.all()], [roles.CONSULTA], "el rol nuevo reemplaza al anterior")
        self.assertFalse(u.is_staff or u.is_active)
        self.assertTrue(u.check_password("clave-de-prueba-123"))

    def test_no_puede_desactivarse_ni_quitarse_el_rol(self):
        r = self.client.post(f"/usuarios/{self.admin.pk}/", self.datos(username="jefa", rol=self.tecnico.pk, is_active="",
                                                                      contrasena="", contrasena2=""))
        self.assertContains(r, "No puede desactivar su propio usuario")
        self.assertContains(r, "No puede quitarse a sí mismo")

    def test_administrador_no_edita_superusuarios(self):
        root = Usuario.objects.create_superuser("root", password="clave-de-prueba-123")
        self.assertEqual(self.client.get(f"/usuarios/{root.pk}/").status_code, 403)
