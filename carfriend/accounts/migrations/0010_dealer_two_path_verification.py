from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_dealerprofile_notify_prefs"),
    ]

    operations = [
        # DealerVerification — two-path core + numbers (all blank so existing rows stay valid).
        migrations.AddField(
            model_name="dealerverification",
            name="aadhaar_number",
            field=models.CharField(blank=True, max_length=12),
        ),
        migrations.AddField(
            model_name="dealerverification",
            name="aoa_number",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AddField(
            model_name="dealerverification",
            name="city",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="dealerverification",
            name="official_email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="dealerverification",
            name="official_mobile",
            field=models.CharField(blank=True, max_length=15),
        ),
        migrations.AddField(
            model_name="dealerverification",
            name="path",
            field=models.CharField(
                blank=True,
                choices=[
                    ("formal", "Path 1 — formal business (GSTIN)"),
                    ("small", "Path 2 — small business (Udyam + Gumasta)"),
                ],
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="dealerverification",
            name="pan_number",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="dealerverification",
            name="tan_number",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AlterField(
            model_name="dealerverification",
            name="gstin",
            field=models.CharField(blank=True, max_length=20),
        ),
        # DealerDocument — doc_type choices now cover both paths (no DB change; state parity).
        migrations.AlterField(
            model_name="dealerdocument",
            name="doc_type",
            field=models.CharField(
                choices=[
                    ("gst_certificate", "GST Certificate"),
                    ("pan_card", "PAN Card"),
                    ("tan_card", "TAN Card"),
                    ("aoa", "Articles of Association (AOA)"),
                    ("gumasta", "Gumasta Dhara / Shop Act licence"),
                    ("udyam", "Udyam Certificate"),
                ],
                max_length=40,
            ),
        ),
        # DealerProfile — drop the dead auction-preference fields.
        migrations.RemoveField(model_name="dealerprofile", name="brand_interest"),
        migrations.RemoveField(model_name="dealerprofile", name="budget_max"),
        migrations.RemoveField(model_name="dealerprofile", name="budget_min"),
        migrations.RemoveField(model_name="dealerprofile", name="preferences"),
    ]
