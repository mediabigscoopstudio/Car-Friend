import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("deals", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="deal",
            name="gst_percentage",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=5),
        ),
        migrations.AddField(
            model_name="deal",
            name="gst_amount",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="deal",
            name="additional_charges",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="deal",
            name="cf_commission",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="deal",
            name="grand_total",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name="HandoverChecklist",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("keys_received", models.BooleanField(default=False)),
                ("rc_received", models.BooleanField(default=False)),
                ("insurance_received", models.BooleanField(default=False)),
                ("service_history_received", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("stock_out_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="handovers_completed", to=settings.AUTH_USER_MODEL)),
                ("deal", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="handover", to="deals.deal")),
            ],
        ),
    ]
