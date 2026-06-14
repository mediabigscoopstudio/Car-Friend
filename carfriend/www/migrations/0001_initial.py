from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="HomepageLead",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plate_number", models.CharField(blank=True, max_length=20)),
                ("make", models.CharField(blank=True, max_length=100)),
                ("model", models.CharField(blank=True, max_length=100)),
                ("year", models.IntegerField(blank=True, null=True)),
                ("fuel_type", models.CharField(blank=True, max_length=30)),
                ("phone", models.CharField(max_length=15)),
                ("est_price_low", models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True)),
                ("est_price_high", models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True)),
                ("source", models.CharField(choices=[("plate", "Plate lookup"), ("brand", "Brand selection")], default="plate", max_length=10)),
                ("is_contacted", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Homepage lead",
                "verbose_name_plural": "Homepage leads",
                "ordering": ["-created_at"],
            },
        ),
    ]
