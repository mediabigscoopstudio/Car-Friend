from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("auctions", "0003_ocbmessage"),
    ]

    operations = [
        migrations.AddField(
            model_name="ocblisting",
            name="sales_associate",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="sales_ocbs",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
