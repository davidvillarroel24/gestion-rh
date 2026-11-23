from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from core import alcance


@login_required
def visor(request):
    # El personal de licencias trabaja sin mapa (D31): va a su página.
    if alcance.ve_licencias(request.user) and not alcance.ve_proyectos(request.user):
        return redirect("licencias:inicio")
    return render(request, "visor/visor.html")
