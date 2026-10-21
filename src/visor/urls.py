from django.urls import path

from . import api, views

app_name = "visor"

urlpatterns = [
    path("", views.visor, name="visor"),
    path("api/config/", api.config, name="api_config"),
    path("api/geometrias/", api.geometrias, name="api_geometrias"),
    path("api/geometrias/<int:pk>/", api.geometria, name="api_geometria"),
    path("api/proyectos/", api.proyectos, name="api_proyectos"),
    path("api/proyectos/<int:pk>/", api.proyecto, name="api_proyecto"),
]
