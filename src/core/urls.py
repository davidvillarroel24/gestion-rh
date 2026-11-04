from django.contrib.auth import views as auth_views
from django.urls import path

from . import catalogos, usuarios, views

app_name = "core"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("ingresar/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="ingresar"),
    path("salir/", auth_views.LogoutView.as_view(), name="salir"),
    path("usuarios/", usuarios.lista, name="usuarios"),
    path("usuarios/nuevo/", usuarios.formulario, name="usuario_nuevo"),
    path("usuarios/<int:pk>/", usuarios.formulario, name="usuario"),
    path("catalogos/<slug:nombre>/", catalogos.catalogo, name="catalogo"),
    path("salud/", views.salud, name="salud"),
]
