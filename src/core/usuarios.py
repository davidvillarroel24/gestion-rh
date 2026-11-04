"""
Gestión de usuarios para el Administrador (/usuarios/): crear, asignar rol y
área (unidades o municipios), activar/desactivar y cambiar la contraseña.

Reemplaza a la vista de usuarios de «Gestión licencias». El rol es un grupo
(core/roles.py) y el área es el alcance (core/alcance.py). Los usuarios no se
borran: se desactivan (quedan en la auditoría).
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from territorio.models import Municipio

from . import alcance, roles
from .models import Unidad, Usuario

# Roles que necesitan entrar a la administración de Django (ahí se editan proyectos y catálogos).
SIN_ADMINISTRACION = {roles.CONSULTA}


class UsuarioForm(forms.ModelForm):
    rol = forms.ModelChoiceField(Group.objects.filter(name__in=roles.ROLES).order_by("name"), label="Rol",
                                 empty_label="Elija…")
    contrasena = forms.CharField(label="Contraseña", required=False, strip=False, widget=forms.PasswordInput(render_value=False),
                                 help_text="Al editar, déjela vacía para no cambiarla.")
    contrasena2 = forms.CharField(label="Repetir contraseña", required=False, strip=False, widget=forms.PasswordInput)

    class Meta:
        model = Usuario
        fields = ["first_name", "last_name", "username", "email", "is_active", "unidades", "municipios"]
        labels = {"is_active": "Activo (puede ingresar)", "unidades": "Áreas que gestiona",
                  "municipios": "Municipios que atiende"}
        help_texts = {"username": "Con este nombre ingresa al sistema.",
                      "unidades": "Técnico de unidad: solo ve y edita los proyectos de estas áreas.",
                      "municipios": "Encargado municipal: solo ve los proyectos de estos municipios."}
        widgets = {"unidades": forms.CheckboxSelectMultiple, "municipios": forms.CheckboxSelectMultiple}

    def __init__(self, *args, editor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.editor = editor
        self.fields["unidades"].queryset = Unidad.objects.filter(activo=True).order_by("nombre")
        self.fields["municipios"].queryset = Municipio.objects.order_by("nombre")
        self.fields["first_name"].required = True
        if self.instance.pk:
            self.fields["rol"].initial = self.instance.groups.filter(name__in=roles.ROLES).first()
        else:
            self.fields["contrasena"].required = True
            self.fields["contrasena2"].required = True
            self.fields["contrasena"].help_text = ""

    def clean(self):
        datos = super().clean()
        rol = datos.get("rol")
        if rol and rol.name == roles.TECNICO and not datos.get("unidades"):
            self.add_error("unidades", "Un técnico de unidad necesita al menos un área.")
        if rol and rol.name == roles.ENCARGADO_MUNICIPAL and not datos.get("municipios"):
            self.add_error("municipios", "Un encargado municipal necesita al menos un municipio.")
        if self.instance.pk and self.instance == self.editor:
            if not datos.get("is_active"):
                self.add_error("is_active", "No puede desactivar su propio usuario.")
            if rol and rol.name != roles.ADMINISTRADOR and not self.editor.is_superuser:
                self.add_error("rol", "No puede quitarse a sí mismo el rol de Administrador.")
        clave, clave2 = datos.get("contrasena"), datos.get("contrasena2")
        if clave or clave2:
            if clave != clave2:
                self.add_error("contrasena2", "Las contraseñas no coinciden.")
            else:
                try:
                    validate_password(clave, self.instance)
                except ValidationError as e:
                    self.add_error("contrasena", e)
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=False)
        rol = self.cleaned_data["rol"]
        usuario.is_staff = rol.name not in SIN_ADMINISTRACION
        if self.cleaned_data.get("contrasena"):
            usuario.set_password(self.cleaned_data["contrasena"])
        usuario.save()
        self.save_m2m()
        # El rol reemplaza a los roles anteriores (otros grupos ajenos a los roles se conservan).
        usuario.groups.remove(*usuario.groups.filter(name__in=roles.ROLES))
        usuario.groups.add(rol)
        return usuario


def _solo_administrador(request):
    if not alcance.es_administrador(request.user):
        raise PermissionDenied


@login_required
def lista(request):
    _solo_administrador(request)
    usuarios = Usuario.objects.prefetch_related("groups", "unidades", "municipios").order_by("-is_active", "first_name", "username")
    q = request.GET.get("q", "").strip()
    if q:
        usuarios = usuarios.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
                                   | Q(email__icontains=q))
    rol = request.GET.get("rol", "")
    if rol:
        usuarios = usuarios.filter(groups__name=rol)
    estado = request.GET.get("estado", "")
    if estado in ("activos", "inactivos"):
        usuarios = usuarios.filter(is_active=estado == "activos")
    return render(request, "core/usuarios.html", {"usuarios": usuarios, "roles": list(roles.ROLES), "q": q, "rol": rol,
                                                  "estado": estado})


@login_required
def formulario(request, pk=None):
    _solo_administrador(request)
    usuario = get_object_or_404(Usuario, pk=pk) if pk else None
    if usuario and usuario.is_superuser and not request.user.is_superuser:
        raise PermissionDenied  # un Administrador no edita superusuarios
    form = UsuarioForm(request.POST or None, instance=usuario, editor=request.user)
    if request.method == "POST" and form.is_valid():
        guardado = form.save()
        messages.success(request, f"Usuario «{guardado}» {'actualizado' if usuario else 'creado'}.")
        return redirect("core:usuarios")
    return render(request, "core/usuario_form.html", {
        "form": form, "usuario": usuario, "tecnico": roles.TECNICO, "encargado": roles.ENCARGADO_MUNICIPAL,
        "campos_datos": [form[n] for n in ("first_name", "last_name", "username", "email")],
        "nombres_rol": {str(g.pk): g.name for g in form.fields["rol"].queryset},
    })
