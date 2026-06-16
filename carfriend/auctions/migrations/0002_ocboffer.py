import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auctions", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OCBOffer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("price", models.PositiveIntegerField()),
                ("notes", models.TextField(blank=True)),
                ("is_selected", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("dealer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ocb_dealer_offers", to=settings.AUTH_USER_MODEL)),
                ("ocb_listing", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="offers", to="auctions.ocblisting")),
                ("submitted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ocb_offers_submitted", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-price", "-created_at"]},
        ),
    ]
