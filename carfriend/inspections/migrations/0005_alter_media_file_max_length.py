from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inspections", "0004_inspectionmedia_needs_transcode"),
    ]

    operations = [
        migrations.AlterField(
            model_name="inspectionmedia",
            name="file",
            field=models.FileField(blank=True, max_length=255, null=True, upload_to="inspections/media/raw/"),
        ),
        migrations.AlterField(
            model_name="inspectionmedia",
            name="webp_file",
            field=models.ImageField(blank=True, max_length=255, null=True, upload_to="inspections/media/webp/"),
        ),
        migrations.AlterField(
            model_name="inspectionmedia",
            name="mp4_file",
            field=models.FileField(blank=True, max_length=255, null=True, upload_to="inspections/media/mp4/"),
        ),
        migrations.AlterField(
            model_name="inspectionmedia",
            name="masked_file",
            field=models.ImageField(blank=True, max_length=255, null=True, upload_to="inspections/media/masked/"),
        ),
    ]
