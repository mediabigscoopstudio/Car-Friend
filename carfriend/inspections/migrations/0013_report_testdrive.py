from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inspections", "0011_report_disposition_exhaust_ratings"),
    ]

    operations = [
        migrations.AddField("inspectionreport", "is_drivable",
                            models.BooleanField(null=True, blank=True)),
        migrations.AddField("inspectionreport", "issue_description",
                            models.TextField(blank=True, default="")),
        migrations.AddField("inspectionreport", "towing_needed",
                            models.BooleanField(null=True, blank=True)),
        migrations.AddField("inspectionreport", "gps_route",
                            models.JSONField(default=list, blank=True)),
        migrations.AddField("inspectionreport", "distance_km",
                            models.FloatField(null=True, blank=True)),
        migrations.AddField("inspectionreport", "duration_seconds",
                            models.PositiveIntegerField(null=True, blank=True)),
        migrations.AddField("inspectionreport", "route_start_lat",
                            models.FloatField(null=True, blank=True)),
        migrations.AddField("inspectionreport", "route_start_lng",
                            models.FloatField(null=True, blank=True)),
        migrations.AddField("inspectionreport", "route_end_lat",
                            models.FloatField(null=True, blank=True)),
        migrations.AddField("inspectionreport", "route_end_lng",
                            models.FloatField(null=True, blank=True)),
        migrations.AddField("inspectionreport", "suspension_condition",
                            models.CharField(blank=True, default="", max_length=10,
                                             choices=[("abnormal", "Abnormal"), ("normal", "Normal"), ("weak", "Weak")])),
        migrations.AddField("inspectionreport", "brake_condition",
                            models.CharField(blank=True, default="", max_length=10,
                                             choices=[("abnormal", "Abnormal"), ("normal", "Normal"), ("weak", "Weak")])),
    ]
