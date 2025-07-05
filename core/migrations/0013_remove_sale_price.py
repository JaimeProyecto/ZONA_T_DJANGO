from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "00YY_anterior"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="product",
            name="sale_price",
        ),
    ]
