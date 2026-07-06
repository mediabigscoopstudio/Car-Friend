from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("deals", "0002_finalization_handover"),
    ]

    operations = [
        migrations.AddField(
            model_name="dealagreement",
            name="dealer_signed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="dealagreement",
            name="seller_signed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
