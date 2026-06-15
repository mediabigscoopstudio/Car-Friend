from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kyc", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="kycverification",
            name="result_name",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
