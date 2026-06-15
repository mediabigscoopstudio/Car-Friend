import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import accounts.models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_user_guest_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DealerVerification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("business_name", models.CharField(max_length=200)),
                ("gstin", models.CharField(max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending approval"), ("approved", "Approved"), ("rejected", "Rejected")], default="pending", max_length=10)),
                ("reject_reason", models.TextField(blank=True)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("dealer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dealer_verifications", to=settings.AUTH_USER_MODEL)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dealer_reviews", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-submitted_at"]},
        ),
        migrations.CreateModel(
            name="DealerDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("doc_type", models.CharField(choices=[("gst_certificate", "GST Certificate"), ("pan_card", "PAN Card"), ("tan_card", "TAN Card"), ("aoa", "Articles of Association (AOA)")], max_length=40)),
                ("file", models.FileField(storage=accounts.models.protected_storage, upload_to="dealer_docs/")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                ("verification", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documents", to="accounts.dealerverification")),
            ],
            options={"ordering": ["doc_type"]},
        ),
    ]
