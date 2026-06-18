from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vehicles", "0003_alter_vehicle_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="vehicle",
            name="condition_grade",
            field=models.CharField(blank=True, max_length=1),
        ),
    ]
