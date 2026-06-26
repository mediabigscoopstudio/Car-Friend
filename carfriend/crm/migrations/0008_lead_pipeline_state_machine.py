from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


STAGE_CHOICES = [
    ("new", "New"),
    ("qualified", "Qualified"),
    ("unqualified", "Un-Qualified"),
    ("inspection_scheduled", "Inspection Scheduled"),
    ("inspection_in_progress", "Inspection In Progress"),
    ("inspection_done", "Report Submitted"),
    ("admin_approved", "Admin Approved"),
    ("assigned", "Assigned"),
    ("negotiation", "Negotiation"),
    ("auction_created", "Auction Created"),
    ("auction_live", "Auction Live"),
    ("auction_closed", "Auction Closed"),
    ("seller_approved", "Seller Approved"),
    ("ocb_in_progress", "OCB In Progress"),
    ("agreement_signed", "Agreement Signed"),
    ("handed_to_procurement", "Handed To Procurement"),
    ("closed", "Closed"),
]


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("crm", "0007_leadnote"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lead",
            name="stage",
            field=models.CharField(choices=STAGE_CHOICES, default="new", max_length=30),
        ),
        migrations.AddField(
            model_name="lead",
            name="assigned_associate",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="allocated_leads", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="lead",
            name="allocated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lead",
            name="allocated_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="leads_allocated_by_me", to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name="LeadAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("at", models.DateTimeField(auto_now_add=True)),
                ("from_associate", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="lead_allocations_from", to=settings.AUTH_USER_MODEL)),
                ("to_associate", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="lead_allocations_to", to=settings.AUTH_USER_MODEL)),
                ("by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="lead_allocations_by", to=settings.AUTH_USER_MODEL)),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="allocations", to="crm.lead")),
            ],
            options={"ordering": ["-at"]},
        ),
        migrations.CreateModel(
            name="LeadStatusEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("from_status", models.CharField(blank=True, max_length=30)),
                ("to_status", models.CharField(max_length=30)),
                ("trigger", models.CharField(max_length=40)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="lead_status_events", to=settings.AUTH_USER_MODEL)),
                ("lead", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_events", to="crm.lead")),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
