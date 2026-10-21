from django.contrib import admin
from django.urls import include, path

from proyectos.views import archivo_media

admin.site.site_header = "Gestión RH — SDMAyRH"
admin.site.site_title = "Gestión RH"
admin.site.index_title = "Administración"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("territorio/", include("territorio.urls")),
    path("proyectos/", include("proyectos.urls")),
    path("visor/", include("visor.urls")),
    # Archivos subidos: siempre pasan por Django para verificar permisos (no son públicos).
    path("media/<path:ruta>", archivo_media, name="archivo_media"),
    path("", include("core.urls")),
]
