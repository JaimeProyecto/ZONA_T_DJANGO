from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from django.contrib.auth.models import Group  # ✅ Mover aquí el import
        from django.db.utils import OperationalError

        try:
            Group.objects.get_or_create(name="admin")
            Group.objects.get_or_create(name="vendedor")
        except OperationalError:
            pass
