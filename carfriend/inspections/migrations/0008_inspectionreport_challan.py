from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inspections", "0007_checkpointphoto"),
    ]

    operations = [
        migrations.AddField(
            model_name="inspectionreport",
            name="challan_data",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inspectionreport",
            name="challan_total_pending",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="inspectionreport",
            name="challan_count",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="inspectionreport",
            name="challan_fetched_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inspectionreport",
            name="challan_fetch_status",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
    ]
