from django.urls import path

from . import views

app_name = "reportes"

urlpatterns = [
    path("", views.pagina, name="pagina"),
    path("api/", views.datos, name="datos"),
    path("excel/", views.excel, name="excel"),
    path("ficha/", views.ficha_tecnica, name="ficha"),
    path("ficha/excel/", views.ficha_excel, name="ficha_excel"),
]
