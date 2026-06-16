from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0003_remove_inspectionjob"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lead",
            name="stage",
            field=models.CharField(
                default="new",
                max_length=30,
                choices=[
                    ("new", "New"),
                    ("qualified", "Qualified"),
                    ("unqualified", "Un-Qualified"),
                    ("inspection_scheduled", "Inspection Scheduled"),
                    ("inspection_done", "Inspection Done"),
                    ("admin_approved", "Admin Approved"),
                    ("negotiation", "Negotiation"),
                    ("auction_created", "Auction Created"),
                    ("closed", "Closed"),
                ],
            ),
        ),
    ]
