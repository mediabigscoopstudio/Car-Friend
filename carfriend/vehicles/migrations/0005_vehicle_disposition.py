from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vehicles", "0004_vehicle_condition_grade"),
    ]

    operations = [
        migrations.AddField(
            model_name="vehicle",
            name="disposition",
            field=models.CharField(blank=True, default="", max_length=10,
                                   choices=[("auction", "Auction"), ("scrap", "Scrap")]),
        ),
    ]
