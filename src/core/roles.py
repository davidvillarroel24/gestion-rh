"""
Roles del sistema = grupos de Django, con permisos declarados acá.

Se sincronizan solos después de cada `migrate` (ver CoreConfig.ready), así que
al agregar modelos nuevos basta con sumarlos a este diccionario. Un permiso
quitado de acá también se quita del grupo.

Formato: "app.modelo" o "app.*" (todos los modelos de la app) -> acciones.
Los modelos de historial (auditoría) y los usuarios nunca entran por "app.*".
"""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

ADMINISTRADOR = "Administrador"
TECNICO = "Técnico de unidad"
ENCARGADO_MUNICIPAL = "Encargado municipal"
FUNCIONARIO_LICENCIAS = "Funcionario de licencias"
CONSULTA = "Consulta"

VER = ["view"]
EDITAR = ["view", "add", "change"]

BORRAR = ["view", "add", "change", "delete"]

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
        # Proyectos de sus unidades, con todo lo que cuelga de ellos. El proyecto
        # en sí no se borra (tiene borrado lógico); sus partes sí.
        "proyectos.*": BORRAR,
        "proyectos.proyecto": EDITAR,
    },
    ENCARGADO_MUNICIPAL: {
        # Ve los proyectos de sus municipios; carga datos de producción/beneficiarios,
        # bitácora y documentos. No toca financiamiento ni catálogos.
        "territorio.*": VER,
        "core.*": VER,
        "proyectos.*": VER,
        "proyectos.medicion": EDITAR,
        "proyectos.evento": EDITAR,
        "proyectos.documento": EDITAR,
    },
    FUNCIONARIO_LICENCIAS: {
        "territorio.*": VER,
        "core.*": VER,
        "core.tipodocumento": EDITAR,
        "core.persona": EDITAR,
        "proyectos.proyecto": VER,
    },
    CONSULTA: {
        "territorio.*": VER,
        "core.*": VER,
        "proyectos.*": VER,
    },
}

EXCLUIDOS_DE_COMODIN = {"usuario"}


def _permisos(definicion):
    if definicion == "__all__":
        return set(Permission.objects.all())
    # Primero los comodines y después las entradas específicas, que los REEMPLAZAN
    # para ese modelo (así "proyectos.proyecto": EDITAR le quita el borrar que da "proyectos.*").
    acciones_por_modelo = {}
    for patron, acciones in sorted(definicion.items(), key=lambda par: not par[0].endswith(".*")):
        app, modelo = patron.split(".")
        cts = ContentType.objects.filter(app_label=app)
        if modelo == "*":
            cts = cts.exclude(model__startswith="historical").exclude(model__in=EXCLUIDOS_DE_COMODIN)
        else:
            cts = cts.filter(model=modelo)
        for ct in cts:
            acciones_por_modelo[ct] = acciones

    permisos = set()
    for ct, acciones in acciones_por_modelo.items():
        permisos.update(Permission.objects.filter(
            content_type=ct, codename__in=[f"{accion}_{ct.model}" for accion in acciones]
        ))
    return permisos


def sincronizar_roles(**kwargs):
    for nombre, definicion in ROLES.items():
        grupo, _ = Group.objects.get_or_create(name=nombre)
        grupo.permissions.set(_permisos(definicion))
