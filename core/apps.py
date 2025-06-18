"""
Configuración de la aplicación `core`: registra los handlers de señales tras migraciones.
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """
    CoreConfig: al arrancar, importa el módulo de señales para ejecutar
    la lógica de creación de grupos después de aplicar migraciones.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Importamos el módulo de signals para que se conecten los receivers
        import core.signals  # noqa: F401
