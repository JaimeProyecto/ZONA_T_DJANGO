from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group


class Command(BaseCommand):
    help = "Crea los grupos de usuario y algunos usuarios iniciales"

    def handle(self, *args, **options):
        # Crear grupos si no existen
        admin_group, _ = Group.objects.get_or_create(name="admin")
        vendedor_group, _ = Group.objects.get_or_create(name="vendedor")

        # Crear usuario administrador
        if not User.objects.filter(username="admin").exists():
            admin_user = User.objects.create_superuser(
                username="admin", email="admin@zonat.com", password="admin123"
            )
            admin_user.groups.add(admin_group)
            self.stdout.write(self.style.SUCCESS("🛠 Usuario admin creado."))

        # Crear usuario vendedor
        if not User.objects.filter(username="vendedor").exists():
            vendedor_user = User.objects.create_user(
                username="vendedor", email="vendedor@zonat.com", password="vendedor123"
            )
            vendedor_user.groups.add(vendedor_group)
            self.stdout.write(self.style.SUCCESS("🛠 Usuario vendedor creado."))

        self.stdout.write(
            self.style.SUCCESS("✅ Grupos y usuarios iniciales creados correctamente.")
        )
