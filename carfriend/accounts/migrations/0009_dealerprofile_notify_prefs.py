from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_sellerprofile_payout_prefs"),
    ]

    operations = [
        migrations.AddField(
            model_name="dealerprofile",
            name="notify_email",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="dealerprofile",
            name="notify_push",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="dealerprofile",
            name="notify_sms",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="dealerprofile",
            name="notify_whatsapp",
            field=models.BooleanField(default=True),
        ),
    ]
