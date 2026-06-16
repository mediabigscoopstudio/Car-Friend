from django.db import migrations, models


class Migration(migrations.Migration):
    """Capture the Vehicle.id type drift: 0002 created it as AutoField, but the
    app/project default is BigAutoField. This is the migration makemigrations
    wants. Django alters the dependent FK columns automatically."""

    dependencies = [
        ("vehicles", "0002_vehicle_v2"),
    ]

    operations = [
        migrations.AlterField(
            model_name="vehicle",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
    ]
