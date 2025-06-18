# core/signals.py
from django.apps import apps
from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def create_default_groups(sender, **kwargs):
    """
    Después de migrar la app 'auth', asegura que existan
    los grupos 'admin' y 'vendedor'.
    """
    # Sólo nos importa la señal tras migrar auth
    if sender.label == "auth":
        Group = apps.get_model("auth", "Group")
        Group.objects.get_or_create(name="admin")
        Group.objects.get_or_create(name="vendedor")
