from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inspections", "0010_report_hero_wrapup_insurance"),
    ]

    operations = [
        migrations.AddField(
            model_name="inspectionreport",
            name="disposition",
            field=models.CharField(blank=True, default="", max_length=10,
                                   choices=[("auction", "Auction"), ("scrap", "Scrap")]),
        ),
        migrations.AddField(
            model_name="inspectionreport",
            name="exhaust_smoke",
            field=models.CharField(blank=True, default="", max_length=10,
                                   choices=[("white", "White"), ("black", "Black"), ("none", "No Smoke")]),
        ),
        migrations.AddField(model_name="inspectionreport", name="rating_exterior",
                            field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="inspectionreport", name="rating_interior",
                            field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="inspectionreport", name="rating_engine",
                            field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="inspectionreport", name="rating_suspension",
                            field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="inspectionreport", name="rating_ac",
                            field=models.PositiveSmallIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="inspectionreport", name="rating_brake",
                            field=models.PositiveSmallIntegerField(blank=True, null=True)),
    ]
