from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    name = "core"
    verbose_name = "Núcleo"

    def ready(self):
        from .roles import sincronizar_roles

        # Después de cada migrate: crea/actualiza los grupos de roles con sus permisos.
        post_migrate.connect(sincronizar_roles, dispatch_uid="core.sincronizar_roles")
