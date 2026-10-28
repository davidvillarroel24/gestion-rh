"""
Deshacer una importación aplicada, en orden inverso:
- lo CREADO se borra;
- lo ACTUALIZADO vuelve a su versión anterior (historial de auditoría), pero
  solo si nadie lo modificó después de la importación;
- las RELACIONES agregadas (municipios del proyecto) se quitan.
Si algo no se puede deshacer, no se deshace nada y se explica qué lo impide.
"""

from django.db import transaction
from django.db.models import ProtectedError
from django.utils import timezone

from territorio.models import Municipio
from territorio.servicios import recalcular_agregados

from .models import Cambio, Importacion


def puede_revertir(importacion, usuario):
    return importacion.estado == Importacion.APLICADA and (
        usuario.is_superuser or importacion.usuario_id == usuario.pk or usuario.groups.filter(name="Administrador").exists()
    )


def revertir(importacion):
    problemas = []
    limites_tocados = False
    with transaction.atomic():
        for cambio in importacion.cambios.select_related("tipo_contenido").order_by("-id"):
            modelo = cambio.tipo_contenido.model_class()
            obj = modelo.objects.filter(pk=cambio.objeto_id).first()
            nombre = f"{modelo._meta.verbose_name} «{obj or cambio.objeto_id}»"

            if cambio.accion == Cambio.CREADO:
                if obj is None:
                    continue  # ya no existe (p. ej. se borró junto con su proyecto)
                try:
                    obj.delete()
                except ProtectedError:
                    problemas.append(f"{nombre.capitalize()} ya se usa en otros registros cargados después.")

            elif cambio.accion == Cambio.ACTUALIZADO:
                if obj is None:
                    problemas.append(f"{nombre.capitalize()} ya no existe.")
                    continue
                ultima = obj.history.order_by("-history_id").values_list("history_id", flat=True).first()
                if ultima != cambio.version_importada:
                    problemas.append(f"{nombre.capitalize()} fue modificado después de la importación.")
                    continue
                anterior = obj.history.model.objects.get(history_id=cambio.version_previa).instance
                anterior.save()
                limites_tocados |= modelo is Municipio

            elif cambio.accion == Cambio.RELACION and obj is not None:
                obj.municipios.remove(cambio.extra["municipio"])

        if problemas:
            transaction.set_rollback(True)
            return problemas

        if limites_tocados:
            recalcular_agregados()
        importacion.estado = Importacion.REVERTIDA
        importacion.revertida_en = timezone.now()
        importacion.save()
    return []
