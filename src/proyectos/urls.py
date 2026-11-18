from django.urls import path

from . import edicion, views

app_name = "proyectos"

urlpatterns = [
    path("nuevo/", edicion.nuevo, name="nuevo"),
    path("<int:pk>/editar/", edicion.editar, name="editar"),
    path("documentos/<int:pk>/descargar/", views.descargar_documento, name="descargar_documento"),
]
