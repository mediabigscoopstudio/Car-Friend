import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inspections", "0006_inspectionmedia_transcoded"),
    ]

    operations = [
        migrations.CreateModel(
            name="CheckpointPhoto",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("section", models.CharField(max_length=40)),
                ("checkpoint_key", models.CharField(max_length=120)),
                ("image", models.ImageField(max_length=255, upload_to="inspections/media/checkpoints/webp/")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="checkpoint_photos", to="inspections.inspectionreport")),
            ],
            options={
                "ordering": ["uploaded_at"],
            },
        ),
    ]
