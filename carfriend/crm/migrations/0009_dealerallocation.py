from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("crm", "0008_lead_pipeline_state_machine"),
    ]

    operations = [
        migrations.CreateModel(
            name="DealerAllocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("at", models.DateTimeField(auto_now_add=True)),
                ("by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dealer_allocations_by", to=settings.AUTH_USER_MODEL)),
                ("dealer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dealer_allocations", to=settings.AUTH_USER_MODEL)),
                ("from_associate", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dealer_allocations_from", to=settings.AUTH_USER_MODEL)),
                ("to_associate", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dealer_allocations_to", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-at"]},
        ),
    ]
