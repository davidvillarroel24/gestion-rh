from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import Entidad, Persona, TipoDocumento, TipoEvento, TipoFuente, Unidad, Usuario
from .texto import normalizar


class CatalogoForm(forms.ModelForm):
    """Avisa si el nombre se parece a uno existente; hay que confirmar para crearlo igual."""

    confirmar_parecido = forms.BooleanField(
        required=False, label="Crear de todos modos",
        help_text="Marcar solo si el valor es realmente distinto a los parecidos que se indican.",
    )

    def clean(self):
        datos = super().clean()
        nombre = datos.get("nombre")
        modelo = type(self.instance)
        exacto = nombre and modelo.objects.filter(clave=normalizar(nombre)).exclude(pk=self.instance.pk).exists()
        # Un duplicado exacto lo rechaza el modelo; acá solo se avisa de los parecidos.
        if nombre and not exacto and not datos.get("confirmar_parecido") and "nombre" not in self.errors:
            parecidos = modelo.parecidos(nombre, excluir_pk=self.instance.pk)
            if parecidos:
                lista = ", ".join(f"«{p.nombre}»" for p in parecidos)
                self.add_error("nombre", f"Se parece a: {lista}. Use uno existente o marque «Crear de todos modos».")
        return datos


class CatalogoAdmin(SimpleHistoryAdmin):
    form = CatalogoForm
    list_display = ["nombre", "activo"]
    list_filter = ["activo"]
    search_fields = ["nombre"]


for modelo in (Unidad, TipoFuente, TipoDocumento, TipoEvento):
    admin.site.register(modelo, CatalogoAdmin)


@admin.register(Entidad)
class EntidadAdmin(CatalogoAdmin):
    list_display = ["nombre", "tipo_fuente", "municipio", "activo"]
    list_filter = ["tipo_fuente", "activo"]
    autocomplete_fields = ["municipio"]


@admin.register(Persona)
class PersonaAdmin(SimpleHistoryAdmin):
    list_display = ["nombre", "ci", "telefono", "correo"]
    search_fields = ["nombre", "ci"]


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin, SimpleHistoryAdmin):
    list_display = ["username", "first_name", "last_name", "roles", "is_active"]
    list_filter = ["groups", "is_active", "is_staff"]
    filter_horizontal = ["groups", "unidades", "municipios"]
    fieldsets = UserAdmin.fieldsets[:2] + (
        ("Rol", {
            "fields": ["groups", "is_active", "is_staff", "is_superuser"],
            "description": "El rol es el grupo. «Staff» permite entrar a esta administración.",
        }),
        ("Alcance", {
            "fields": ["unidades", "municipios"],
            "description": "Técnico de unidad → unidades. Encargado municipal → municipios.",
        }),
        ("Fechas", {"fields": ["last_login", "date_joined"]}),
    )

    @admin.display(description="Roles")
    def roles(self, obj):
        return ", ".join(obj.groups.values_list("name", flat=True)) or "—"
