from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_dealer_allocation_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="sellerprofile",
            name="bank_account_name",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AddField(
            model_name="sellerprofile",
            name="bank_account_number",
            field=models.CharField(blank=True, max_length=34),
        ),
        migrations.AddField(
            model_name="sellerprofile",
            name="bank_ifsc",
            field=models.CharField(blank=True, max_length=15),
        ),
        migrations.AddField(
            model_name="sellerprofile",
            name="bank_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="sellerprofile",
            name="notify_email",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="sellerprofile",
            name="notify_push",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="sellerprofile",
            name="notify_sms",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="sellerprofile",
            name="notify_whatsapp",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="sellerprofile",
            name="upi_id",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
