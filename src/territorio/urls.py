from django.urls import path

from . import views

app_name = "territorio"

urlpatterns = [
    path("<str:capa>.geojson", views.capa_geojson, name="capa_geojson"),
]
