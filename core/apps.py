"""Configuración de la aplicación `core`, para inicializar grupos tras la migración."""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """CoreConfig: crea grupos por defecto (‘admin’, ‘vendedor’) después de migrar."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        """
        Se ejecuta después de cargar las apps.
        Hacemos el import aquí para que no haya consultas a BD al iniciarse,
        y capturamos errores si la tabla aún no existe.
        """
        from django.db.utils import OperationalError, ProgrammingError
        from django.contrib.auth.models import Group

        try:
            Group.objects.get_or_create(name="admin")
            Group.objects.get_or_create(name="vendedor")
        except (OperationalError, ProgrammingError):
            # La tabla auth_group aún no está creada: ignoramos
            pass
