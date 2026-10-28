from django.urls import path

from . import views

app_name = "importador"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("tabular/", views.subir_tabular, name="subir_tabular"),
    path("espacial/", views.subir_espacial, name="subir_espacial"),
    path("<int:pk>/", views.detalle, name="detalle"),
    path("<int:pk>/opciones/", views.opciones_espaciales, name="opciones"),
    path("<int:pk>/confirmar/", views.confirmar, name="confirmar"),
    path("<int:pk>/revertir/", views.deshacer, name="revertir"),
    path("<int:pk>/errores.xlsx", views.errores_xlsx, name="errores"),
    path("<int:pk>/vista-previa.geojson", views.vista_previa, name="vista_previa"),
    path("plantillas/<slug:clave>.xlsx", views.plantilla, name="plantilla"),
    path("exportar/excel/", views.exportar_excel, name="exportar_excel"),
    path("exportar/geojson/", views.exportar_geojson, name="exportar_geojson"),
    path("exportar/kml/", views.exportar_kml, name="exportar_kml"),
]
