# core/signals.py
from django.apps import apps
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.contrib.auth.models import User


@receiver(post_migrate)
def create_default_groups_and_users(sender, **kwargs):
    """
    Después de migrar la app 'auth', asegura que existan:
    - los grupos 'admin' y 'vendedor',
    - y los usuarios base asociados a esos grupos.
    """
    if sender.label == "auth":
        Group = apps.get_model("auth", "Group")

        # Crear grupos si no existen
        admin_group, _ = Group.objects.get_or_create(name="admin")
        vendedor_group, _ = Group.objects.get_or_create(name="vendedor")

        # Crear superusuario (admin)
        if not User.objects.filter(username="admin").exists():
            admin_user = User.objects.create_superuser(
                username="admin", email="admin@example.com", password="admin123"
            )
            admin_user.groups.add(admin_group)
            print("Usuario 'admin' creado.")

        # Crear usuario vendedor
        if not User.objects.filter(username="vendedor").exists():
            vendedor_user = User.objects.create_user(
                username="vendedor",
                email="vendedor@example.com",
                password="vendedor123",
            )
            vendedor_user.groups.add(vendedor_group)
            print("Usuario 'vendedor' creado.")
