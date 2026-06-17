from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inspections", "0003_inspectionvisit_lead_assigned_by_address"),
    ]

    operations = [
        migrations.AddField(
            model_name="inspectionmedia",
            name="needs_transcode",
            field=models.BooleanField(default=False),
        ),
    ]
