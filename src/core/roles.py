"""
Roles del sistema = grupos de Django, con permisos declarados acá.

Se sincronizan solos después de cada `migrate` (ver CoreConfig.ready), así que
al agregar modelos nuevos basta con sumarlos a este diccionario. Un permiso
quitado de acá también se quita del grupo.

Formato: "app.modelo" o "app.*" (todos los modelos de la app) -> acciones.
Los modelos de historial (auditoría) y los usuarios nunca entran por "app.*".
"""

from django.contrib.auth.models import Group, Permission

ADMINISTRADOR = "Administrador"
TECNICO = "Técnico de unidad"
ENCARGADO_MUNICIPAL = "Encargado municipal"
FUNCIONARIO_LICENCIAS = "Funcionario de licencias"
CONSULTA = "Consulta"

VER = ["view"]
EDITAR = ["view", "add", "change"]

ROLES = {
    ADMINISTRADOR: "__all__",
    TECNICO: {
        "territorio.*": VER,
        "core.unidad": VER,
        "core.tipofuente": VER,
        "core.tipodocumento": EDITAR,
        "core.tipoevento": EDITAR,
        "core.entidad": EDITAR,
        "core.persona": EDITAR,
    },
    ENCARGADO_MUNICIPAL: {
        "territorio.*": VER,
        "core.*": VER,
    },
    FUNCIONARIO_LICENCIAS: {
        "territorio.*": VER,
        "core.*": VER,
        "core.tipodocumento": EDITAR,
        "core.persona": EDITAR,
    },
    CONSULTA: {
        "territorio.*": VER,
        "core.*": VER,
    },
}

EXCLUIDOS_DE_COMODIN = {"usuario"}


def _permisos(definicion):
    if definicion == "__all__":
        return set(Permission.objects.all())
    permisos = set()
    for patron, acciones in definicion.items():
        app, modelo = patron.split(".")
        qs = Permission.objects.filter(content_type__app_label=app)
        if modelo == "*":
            qs = qs.exclude(content_type__model__startswith="historical").exclude(
                content_type__model__in=EXCLUIDOS_DE_COMODIN
            )
        else:
            qs = qs.filter(content_type__model=modelo)
        for accion in acciones:
            permisos.update(qs.filter(codename__startswith=f"{accion}_"))
    return permisos


def sincronizar_roles(**kwargs):
    for nombre, definicion in ROLES.items():
        grupo, _ = Group.objects.get_or_create(name=nombre)
        grupo.permissions.set(_permisos(definicion))
