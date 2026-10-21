from django.apps import AppConfig


class ProyectosConfig(AppConfig):
    name = "proyectos"
    verbose_name = "Proyectos"

    def ready(self):
        from core.catalogos import CATALOGOS

        from . import models

        # Catálogos que los formularios pueden ampliar en línea (D18).
        CATALOGOS.update({
            "estados": models.EstadoProyecto,
            "programas": models.Programa,
            "tipos-proyecto": models.TipoProyecto,
            "tipos-elemento": models.TipoElemento,
            "indicadores": models.Indicador,
            "desagregaciones": models.Desagregacion,
            "materiales": models.Material,
            "propositos": models.Proposito,
            "tipos-planta": models.TipoPlanta,
        })
