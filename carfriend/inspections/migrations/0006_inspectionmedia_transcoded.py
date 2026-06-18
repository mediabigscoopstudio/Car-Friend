from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inspections", "0005_alter_media_file_max_length"),
    ]

    operations = [
        migrations.AddField(
            model_name="inspectionmedia",
            name="transcoded",
            field=models.BooleanField(default=False),
        ),
    ]
