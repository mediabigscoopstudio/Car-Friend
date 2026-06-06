import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vehicles', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Drop old models
        migrations.DeleteModel(name='VehicleDocument'),
        migrations.DeleteModel(name='VehiclePhoto'),
        migrations.DeleteModel(name='Vehicle'),

        # Create new Vehicle model
        migrations.CreateModel(
            name='Vehicle',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plate_number', models.CharField(max_length=20, unique=True)),
                ('make', models.CharField(max_length=100)),
                ('model', models.CharField(max_length=100)),
                ('variant', models.CharField(blank=True, max_length=100)),
                ('year', models.IntegerField()),
                ('fuel_type', models.CharField(choices=[('petrol','Petrol'),('diesel','Diesel'),('cng','CNG'),('electric','Electric'),('hybrid','Hybrid')], max_length=20)),
                ('transmission', models.CharField(choices=[('manual','Manual'),('automatic','Automatic')], max_length=20)),
                ('colour', models.CharField(max_length=100)),
                ('registration_date', models.DateField(blank=True, null=True)),
                ('registration_state', models.CharField(blank=True, max_length=100)),
                ('rto', models.CharField(blank=True, max_length=100)),
                ('owner_name', models.CharField(blank=True, max_length=200)),
                ('owner_number', models.IntegerField(default=1)),
                ('chassis_number', models.CharField(blank=True, max_length=100)),
                ('engine_number', models.CharField(blank=True, max_length=100)),
                ('insurance_valid_till', models.DateField(blank=True, null=True)),
                ('is_hypothecated', models.BooleanField(default=False)),
                ('accident_history', models.BooleanField(default=False)),
                ('odometer_km', models.IntegerField(blank=True, null=True)),
                ('last_service_date', models.DateField(blank=True, null=True)),
                ('tyre_condition', models.CharField(blank=True, max_length=100)),
                ('expected_price', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('inspection_address', models.TextField(blank=True)),
                ('preferred_inspection_slot', models.CharField(blank=True, max_length=200)),
                ('rc_document', models.FileField(blank=True, null=True, upload_to='vehicles/docs/')),
                ('insurance_document', models.FileField(blank=True, null=True, upload_to='vehicles/docs/')),
                ('service_history', models.FileField(blank=True, null=True, upload_to='vehicles/docs/')),
                ('noc_document', models.FileField(blank=True, null=True, upload_to='vehicles/docs/')),
                ('status', models.CharField(choices=[('draft','Draft'),('submitted','Submitted'),('inspection_scheduled','Inspection Scheduled'),('inspection_done','Inspection Done'),('approved','Admin Approved'),('in_auction','In Auction'),('sold','Sold'),('rejected','Rejected')], default='submitted', max_length=30)),
                ('inspection_report_ready', models.BooleanField(default=False)),
                ('auction_active', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('seller', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vehicles', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
