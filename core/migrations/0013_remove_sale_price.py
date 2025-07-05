# core/migrations/0013_remove_sale_price.py

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_alter_venta_tipo_pago"),  # tu migración previa real
    ]

    operations = [
        migrations.RemoveField(
            model_name="product",
            name="sale_price",
        ),
    ]
