# Generated by Django 5.2.3 on 2025-06-15 01:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_venta_usuario_alter_cliente_cedula_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="venta",
            name="tipo_pago",
            field=models.CharField(
                choices=[("contado", "Contado"), ("credito", "Crédito")],
                default="contado",
                max_length=10,
            ),
        ),
    ]
