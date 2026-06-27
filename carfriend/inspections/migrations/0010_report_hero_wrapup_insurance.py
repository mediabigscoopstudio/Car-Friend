from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inspections", "0009_vehicleregistrydata"),
    ]

    operations = [
        migrations.AddField(model_name="inspectionreport", name="auction_hero_image",
                            field=models.ImageField(blank=True, null=True, max_length=255, upload_to="inspections/hero/")),
        migrations.AddField(model_name="inspectionreport", name="front_photo",
                            field=models.ImageField(blank=True, null=True, max_length=255, upload_to="inspections/wrapup/")),
        migrations.AddField(model_name="inspectionreport", name="rear_photo",
                            field=models.ImageField(blank=True, null=True, max_length=255, upload_to="inspections/wrapup/")),
        migrations.AddField(model_name="inspectionreport", name="left_photo",
                            field=models.ImageField(blank=True, null=True, max_length=255, upload_to="inspections/wrapup/")),
        migrations.AddField(model_name="inspectionreport", name="right_photo",
                            field=models.ImageField(blank=True, null=True, max_length=255, upload_to="inspections/wrapup/")),
        migrations.AddField(model_name="inspectionreport", name="walkaround_video",
                            field=models.FileField(blank=True, null=True, max_length=255, upload_to="inspections/wrapup/video/")),
        migrations.AddField(model_name="inspectionreport", name="engine_audio",
                            field=models.FileField(blank=True, null=True, max_length=255, upload_to="inspections/wrapup/audio/")),
        migrations.AddField(model_name="inspectionreport", name="final_notes",
                            field=models.TextField(blank=True, default="")),
        migrations.AddField(model_name="inspectionreport", name="insurance_type",
                            field=models.CharField(blank=True, max_length=30)),
        migrations.AddField(model_name="inspectionreport", name="insurer_name",
                            field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="inspectionreport", name="policy_number",
                            field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name="inspectionreport", name="insurance_expiry_month",
                            field=models.CharField(blank=True, max_length=12)),
        migrations.AddField(model_name="inspectionreport", name="insurance_expiry_year",
                            field=models.CharField(blank=True, max_length=4)),
        migrations.AddField(model_name="inspectionreport", name="insurance_photo",
                            field=models.ImageField(blank=True, null=True, max_length=255, upload_to="inspections/insurance/")),
    ]
