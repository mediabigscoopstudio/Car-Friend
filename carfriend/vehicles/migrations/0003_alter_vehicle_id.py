from django.db import migrations, models


class Migration(migrations.Migration):
    """Reconcile Vehicle.id to BigAutoField at the STATE level only.

    0002 created Vehicle.id as AutoField while the app/project default is
    BigAutoField, so makemigrations kept reporting drift. We update Django's
    migration state to BigAutoField but perform NO database operation: the
    actual column stays a 32-bit serial (fine well past this app's scale), and
    we avoid an FK-constraint rebuild that would trip on pre-existing orphaned
    rows (e.g. an auctions_auction pointing at a deleted vehicle). No data is
    touched. A real int->bigint conversion can be done later after cleaning
    orphaned FK references, if ever needed.
    """

    dependencies = [
        ("vehicles", "0002_vehicle_v2"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterField(
                    model_name="vehicle",
                    name="id",
                    field=models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
            ],
            database_operations=[],
        ),
    ]
