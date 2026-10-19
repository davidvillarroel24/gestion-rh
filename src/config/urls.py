from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Gestión RH — SDMAyRH"
admin.site.site_title = "Gestión RH"
admin.site.index_title = "Administración"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("territorio/", include("territorio.urls")),
    path("", include("core.urls")),
]
