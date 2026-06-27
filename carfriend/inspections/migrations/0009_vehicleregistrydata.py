from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inspections", "0008_inspectionreport_challan"),
        ("vehicles", "0004_vehicle_condition_grade"),
    ]

    operations = [
        migrations.CreateModel(
            name="VehicleRegistryData",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reg_number", models.CharField(blank=True, max_length=20)),
                ("raw_json", models.JSONField(blank=True, default=dict)),
                ("owner_name", models.CharField(blank=True, max_length=200)),
                ("source", models.CharField(choices=[("surepass", "Surepass / VAHAN"), ("ocr", "RC OCR"), ("manual", "Manual entry")], default="surepass", max_length=10)),
                ("fetched_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("vehicle", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="registry", to="vehicles.vehicle")),
            ],
        ),
    ]
