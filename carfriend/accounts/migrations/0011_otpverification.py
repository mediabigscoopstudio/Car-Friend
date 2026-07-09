from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_dealer_two_path_verification"),
    ]

    operations = [
        migrations.CreateModel(
            name="OTPVerification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(max_length=15)),
                ("otp_code", models.CharField(max_length=6)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("verified", models.BooleanField(default=False)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
