from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


OCB_STATUS_CHOICES = [
    ("open", "Open"),
    ("offered_to_winner", "Offered to auction winner"),
    ("winner_accepted", "Winner accepted"),
    ("winner_declined", "Winner declined"),
    ("assigned_to_sales", "Assigned to sales associate"),
    ("dealers_contacted", "Dealers contacted"),
    ("seller_accepted", "Seller accepted price"),
    ("agreement", "Agreement"),
    ("accepted", "Accepted (legacy)"),
    ("countered", "Countered (legacy)"),
    ("rejected", "Rejected (legacy)"),
]


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auctions", "0005_backfill_ocb_sales_associate"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ocblisting",
            name="status",
            field=models.CharField(choices=OCB_STATUS_CHOICES, default="open", max_length=20),
        ),
        migrations.AddField(
            model_name="ocblisting",
            name="offered_to",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="ocbs_offered_to_me", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="ocblisting",
            name="winner_responded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ocblisting",
            name="assigned_sales_associate",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="sales_head_ocbs", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="ocblisting",
            name="sales_assigned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="ocblisting",
            name="sales_assigned_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="ocbs_assigned_by_me", to=settings.AUTH_USER_MODEL),
        ),
    ]
