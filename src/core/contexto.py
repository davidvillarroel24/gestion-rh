from . import alcance


def roles(request):
    """Disponible en todas las plantillas: qué módulos y opciones de administración ve el usuario."""
    u = request.user
    return {"es_administrador": alcance.es_administrador(u), "ve_licencias": alcance.ve_licencias(u),
            "ve_proyectos": alcance.ve_proyectos(u), "administra_licencias": alcance.administra_licencias(u)}
