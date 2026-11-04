from . import alcance


def roles(request):
    """Disponible en todas las plantillas: si el usuario ve las opciones de administración."""
    return {"es_administrador": alcance.es_administrador(request.user)}
