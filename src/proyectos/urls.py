from django.urls import path

from . import views

app_name = "proyectos"

urlpatterns = [
    path("documentos/<int:pk>/descargar/", views.descargar_documento, name="descargar_documento"),
]
