from django.urls import path

from . import views

app_name = "licencias"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("configuracion/", views.configuracion, name="configuracion"),
    path("columnas/", views.columnas, name="columnas"),
    path("excel/", views.excel, name="excel"),
]
