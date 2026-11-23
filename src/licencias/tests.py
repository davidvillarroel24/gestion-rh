from datetime import date

from django.contrib.auth.models import Group
from django.test import TestCase

from core import roles
from core.models import Usuario
from core.roles import sincronizar_roles

from .models import AOP, Categoria, ConfiguracionLicencias, Feriado, TipoDocumentoAmbiental, Tramite
from .plazos import vencimiento


class BaseLicencias(TestCase):
    @classmethod
    def setUpTestData(cls):
        sincronizar_roles()

    def usuario(self, nombre, rol=None, superusuario=False):
        if superusuario:
            return Usuario.objects.create_superuser(nombre, password="clave-de-prueba-123")
        u = Usuario.objects.create_user(nombre, password="clave-de-prueba-123")
        if rol:
            u.groups.add(Group.objects.get(name=rol))
        return u


class RolesTests(BaseLicencias):
    def test_roles_separados_de_proyectos(self):
        admin_proyectos = self.usuario("jefa", roles.ADMINISTRADOR)
        self.assertFalse(admin_proyectos.has_perm("licencias.change_tramite"), "el Administrador de proyectos no administra licencias")
        self.client.force_login(admin_proyectos)
        self.assertEqual(self.client.get("/licencias/").status_code, 403)
        self.assertNotContains(self.client.get("/importar/"), 'href="/licencias/"')

    def test_funcionario_entra_directo_y_sin_mapa(self):
        self.client.force_login(self.usuario("recepcion", roles.FUNCIONARIO_LICENCIAS))
        self.assertRedirects(self.client.get("/"), "/licencias/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/visor/"), "/licencias/", fetch_redirect_response=False)
        r = self.client.get("/licencias/")
        self.assertContains(r, "Licencias ambientales")
        self.assertNotContains(r, 'href="/visor/"', msg_prefix="sin enlaces a proyectos ni mapa")
        self.assertEqual(self.client.get("/licencias/configuracion/").status_code, 403, "la configuración es del administrador")

    def test_administrador_de_licencias(self):
        u = self.usuario("jefe-lic", roles.ADMIN_LICENCIAS)
        self.assertTrue(u.has_perm("licencias.delete_tramite"))
        self.assertFalse(u.has_perm("proyectos.change_proyecto"))
        self.client.force_login(u)
        self.assertContains(self.client.get("/licencias/"), 'href="/licencias/configuracion/"')

    def test_superusuario_ve_todo(self):
        self.client.force_login(self.usuario("root", superusuario=True))
        self.assertEqual(self.client.get("/licencias/configuracion/").status_code, 200)
        self.assertRedirects(self.client.get("/"), "/visor/", fetch_redirect_response=False)


class ConfiguracionTests(BaseLicencias):
    def setUp(self):
        self.client.force_login(self.usuario("jefe-lic", roles.ADMIN_LICENCIAS))

    def formset(self, prefijo, filas, iniciales=0):
        datos = {f"{prefijo}-TOTAL_FORMS": str(len(filas)), f"{prefijo}-INITIAL_FORMS": str(iniciales),
                 f"{prefijo}-MIN_NUM_FORMS": "0", f"{prefijo}-MAX_NUM_FORMS": "1000"}
        for i, fila in enumerate(filas):
            datos.update({f"{prefijo}-{i}-{k}": v for k, v in fila.items()})
        return datos

    def test_valores_iniciales(self):
        self.assertTrue(TipoDocumentoAmbiental.objects.filter(sigla="IMA", periodicidad="anual").exists())
        self.assertTrue(TipoDocumentoAmbiental.objects.get(sigla="CNCA").es_consulta_categoria)
        self.assertFalse(Categoria.objects.exists(), "las categorías las escribe el área")

    def test_crear_categoria_con_dias_y_evitar_duplicado(self):
        r = self.client.post("/licencias/configuracion/?seccion=categorias", self.formset("categorias", [
            {"nombre": "CAT 4", "dias": "10", "contar_desde": "presentacion", "activo": "on"}]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Categoria.objects.get().dias, 10)
        r = self.client.post("/licencias/configuracion/?seccion=categorias", self.formset("categorias", [
            {"nombre": "cat 4", "contar_desde": "presentacion", "activo": "on"}]))
        self.assertContains(r, "Ya existe")

    def test_no_borra_categoria_en_uso(self):
        cat = Categoria.objects.create(nombre="OBS")
        Tramite.objects.create(aop=AOP.objects.create(nombre="Edificio X"), categoria=cat)
        r = self.client.post("/licencias/configuracion/?seccion=categorias", self.formset("categorias", [
            {"id": cat.pk, "nombre": "OBS", "contar_desde": "presentacion", "activo": "on", "DELETE": "on"}], iniciales=1),
            follow=True)
        self.assertContains(r, "desactívelo")
        self.assertTrue(Categoria.objects.filter(pk=cat.pk).exists())

    def test_columnas_del_funcionario(self):
        r = self.client.post("/licencias/configuracion/?seccion=general", {"dias_aviso": "7",
                                                                          "columnas_funcionario": ["numero", "aop"]})
        self.assertEqual(r.status_code, 302)
        conf = ConfiguracionLicencias.actual()
        self.assertEqual((conf.dias_aviso, conf.columnas_funcionario), (7, ["numero", "aop"]))


class PlazosTests(BaseLicencias):
    def test_vencimiento_calendario_y_habiles(self):
        aop = AOP.objects.create(nombre="Estación de servicio")
        cat = Categoria.objects.create(nombre="CAT 4", dias=10)
        t = Tramite.objects.create(aop=aop, categoria=cat, fecha_presentacion=date(2026, 11, 2))  # lunes
        self.assertEqual(vencimiento(t), date(2026, 11, 12))
        cat.dias_habiles = True
        cat.save()
        Feriado.objects.create(fecha=date(2026, 11, 4), nombre="Feriado de prueba")
        self.assertEqual(vencimiento(t), date(2026, 11, 17), "10 hábiles sin fines de semana ni el feriado")
        cat.contar_desde = Categoria.RESULTADO
        cat.save()
        self.assertIsNone(vencimiento(t), "sin fecha de resultado no hay vencimiento")
        cat.dias = None
        cat.save()
        self.assertIsNone(Tramite.objects.get(pk=t.pk).vencimiento, "sin días configurados no hay alerta")


class TablaTests(BaseLicencias):
    def setUp(self):
        from datetime import timedelta
        from io import BytesIO

        self.BytesIO = BytesIO
        hoy = date.today()
        ima = TipoDocumentoAmbiental.objects.get(sigla="IMA")
        cnca = TipoDocumentoAmbiental.objects.get(sigla="CNCA")
        cat = Categoria.objects.create(nombre="CAT 4", dias=10)
        self.vencido = Tramite.objects.create(numero="101", aop=AOP.objects.create(nombre="Motel Amasis"), tipo_documento=ima,
                                              categoria=cat, tecnico="GONZALES", fecha_presentacion=hoy - timedelta(days=30))
        self.al_dia = Tramite.objects.create(numero="102", aop=AOP.objects.create(nombre="Edificio Grecos"), tipo_documento=ima,
                                             fecha_presentacion=hoy, tecnico="SOLIZ")
        self.consulta = Tramite.objects.create(numero="5", aop=AOP.objects.create(nombre="Pozo de riego"), tipo_documento=cnca)
        self.borrado = Tramite.objects.create(numero="9", aop=AOP.objects.create(nombre="Borrado"), eliminado=True)

    def test_pestanas_y_resaltado(self):
        self.client.force_login(self.usuario("jefe-lic", roles.ADMIN_LICENCIAS))
        r = self.client.get("/licencias/")
        self.assertContains(r, "Motel Amasis")
        self.assertNotContains(r, "Pozo de riego", msg_prefix="las consultas de categoría van en su pestaña")
        self.assertNotContains(r, "Borrado")
        self.assertContains(r, '<tr class="vencido">', count=1)
        self.assertContains(self.client.get("/licencias/", {"pestana": "consultas"}), "Pozo de riego")
        self.assertContains(self.client.get("/licencias/", {"pestana": "papelera"}), "Borrado")

    def test_filtros_y_orden(self):
        self.client.force_login(self.usuario("jefe-lic", roles.ADMIN_LICENCIAS))
        r = self.client.get("/licencias/", {"tecnico": "gonz"})
        self.assertContains(r, "Motel Amasis")
        self.assertNotContains(r, "Edificio Grecos")
        r = self.client.get("/licencias/", {"q": "grecos"})
        self.assertContains(r, "Edificio Grecos")
        self.assertNotContains(r, "Motel Amasis")
        contenido = self.client.get("/licencias/", {"orden": "numero"}).content.decode()
        self.assertLess(contenido.index("Motel Amasis"), contenido.index("Edificio Grecos"))

    def test_funcionario_columnas_limitadas(self):
        self.client.force_login(self.usuario("recepcion", roles.FUNCIONARIO_LICENCIAS))
        r = self.client.get("/licencias/", {"tecnico": "SOLIZ"})
        self.assertNotContains(r, ">Técnico<", msg_prefix="no ve la columna técnico")
        self.assertContains(r, "Motel Amasis", msg_prefix="no puede filtrar por una columna que no ve")
        self.assertNotContains(r, "?pestana=papelera", msg_prefix="la papelera es del administrador")
        self.assertNotContains(self.client.get("/licencias/", {"pestana": "papelera"}), "Borrado")

    def test_columnas_elegidas_se_recuerdan(self):
        self.client.force_login(self.usuario("recepcion", roles.FUNCIONARIO_LICENCIAS))
        self.client.post("/licencias/columnas/", {"columnas": ["numero", "aop", "tecnico"], "volver": "/licencias/"})
        r = self.client.get("/licencias/")
        self.assertContains(r, ">AOP</a>")
        self.assertNotContains(r, "<th>Municipio</th>")
        self.assertNotContains(r, ">Técnico", msg_prefix="no puede elegir una columna que su rol no permite")

    def test_excel(self):
        from openpyxl import load_workbook

        self.client.force_login(self.usuario("jefe-lic", roles.ADMIN_LICENCIAS))
        r = self.client.get("/licencias/excel/", {"q": "motel"})
        hoja = load_workbook(self.BytesIO(r.content)).active
        self.assertEqual(hoja["A1"].value, "ID")
        self.assertEqual(hoja.max_row, 2)
        self.assertIn("Motel Amasis", [c.value for c in hoja[2]])
        self.assertEqual(hoja["A2"].fill.fgColor.rgb[-6:], "F8D7DA", "el vencido sale resaltado")
