from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404

from core import alcance

from .models import Documento, Proyecto


def _documento_visible(usuario, **filtro):
    if not usuario.has_perm("proyectos.view_documento"):
        raise Http404
    proyectos = alcance.filtrar(Proyecto.objects.vigentes(), usuario, "unidad", "municipios")
    documento = Documento.objects.filter(proyecto__in=proyectos, **filtro).first()
    if documento is None or not documento.archivo:
        raise Http404
    return documento


@login_required
def descargar_documento(request, pk):
    documento = _documento_visible(request.user, pk=pk)
    return FileResponse(documento.archivo.open("rb"), as_attachment=True,
                        filename=documento.archivo.name.rsplit("/", 1)[-1])


@login_required
def archivo_media(request, ruta):
    """Los archivos subidos NO son públicos: /media/... pasa por acá y se verifica el alcance."""
    documento = _documento_visible(request.user, archivo=ruta)
    return FileResponse(documento.archivo.open("rb"), as_attachment=True,
                        filename=documento.archivo.name.rsplit("/", 1)[-1])
