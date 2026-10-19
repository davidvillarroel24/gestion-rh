"""
Alcance de cada usuario: qué unidades y municipios puede ver.

- Superusuario, Administrador, Consulta: todo.
- Técnico de unidad: solo sus unidades (en cualquier municipio).
- Encargado municipal: solo sus municipios (de cualquier unidad).
- Si tiene varios roles, se suma lo que habilita cada uno.

Toda vista o exportación que liste registros debe pasar por `filtrar()`;
así un encargado municipal nunca ve (ni exporta) datos de otro municipio.
"""

from django.db.models import Q

from territorio.models import Municipio

from . import roles
from .models import Unidad


def nombres_de_roles(usuario):
    if not usuario.is_authenticated:
        return set()
    if not hasattr(usuario, "_roles_cache"):
        usuario._roles_cache = set(usuario.groups.values_list("name", flat=True))
    return usuario._roles_cache


def ve_todo(usuario):
    return usuario.is_authenticated and (
        usuario.is_superuser or bool(nombres_de_roles(usuario) & {roles.ADMINISTRADOR, roles.CONSULTA})
    )


def unidades_visibles(usuario):
    if ve_todo(usuario) or roles.ENCARGADO_MUNICIPAL in nombres_de_roles(usuario):
        return Unidad.objects.all()
    if roles.TECNICO in nombres_de_roles(usuario):
        return usuario.unidades.all()
    return Unidad.objects.none()


def municipios_visibles(usuario):
    if ve_todo(usuario) or roles.TECNICO in nombres_de_roles(usuario):
        return Municipio.objects.all()
    if roles.ENCARGADO_MUNICIPAL in nombres_de_roles(usuario):
        return usuario.municipios.all()
    return Municipio.objects.none()


def filtrar(qs, usuario, campo_unidad=None, campo_municipio=None):
    """
    Restringe un queryset al alcance del usuario.

    campo_unidad / campo_municipio: ruta del campo en el modelo, por ejemplo
    filtrar(Proyecto.objects.all(), request.user, "unidad", "municipios").
    Con roles combinados, alcanza con cumplir lo de cualquiera de ellos.
    """
    if ve_todo(usuario):
        return qs
    nombres = nombres_de_roles(usuario)
    condicion = Q(pk__in=[])  # sin un rol con alcance, no ve nada
    if roles.TECNICO in nombres and campo_unidad:
        condicion |= Q(**{f"{campo_unidad}__in": usuario.unidades.all()})
    if roles.ENCARGADO_MUNICIPAL in nombres and campo_municipio:
        condicion |= Q(**{f"{campo_municipio}__in": usuario.municipios.all()})
    return qs.filter(condicion).distinct()
