from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_add_head_roles"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="assigned_sales_associate",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="assigned_dealers", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="user",
            name="dealer_allocated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="dealer_allocated_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="dealer_allocations_by_me", to=settings.AUTH_USER_MODEL),
        ),
    ]
