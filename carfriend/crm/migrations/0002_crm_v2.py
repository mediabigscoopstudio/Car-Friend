import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0001_initial'),
        ('vehicles', '0002_vehicle_v2'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Remove old models (must delete dependents first)
        migrations.DeleteModel(name='NegotiationOffer'),
        migrations.DeleteModel(name='CommunicationLog'),
        migrations.DeleteModel(name='Task'),
        migrations.DeleteModel(name='Lead'),

        # Create new Lead
        migrations.CreateModel(
            name='Lead',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stage', models.CharField(
                    choices=[
                        ('new', 'New'),
                        ('qualified', 'Qualified'),
                        ('inspection_scheduled', 'Inspection Scheduled'),
                        ('inspection_done', 'Inspection Done'),
                        ('admin_approved', 'Admin Approved'),
                        ('negotiation', 'Negotiation'),
                        ('auction_created', 'Auction Created'),
                        ('closed', 'Closed'),
                    ],
                    default='new',
                    max_length=30,
                )),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('vehicle', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lead',
                    to='vehicles.vehicle',
                )),
                ('seller', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='leads',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('assigned_to', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='assigned_leads',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at']},
        ),

        # Create InspectionJob
        migrations.CreateModel(
            name='InspectionJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scheduled_at', models.DateTimeField()),
                ('inspection_address', models.TextField()),
                ('status', models.CharField(
                    choices=[
                        ('scheduled', 'Scheduled'),
                        ('in_progress', 'In Progress'),
                        ('submitted', 'Report Submitted'),
                        ('approved', 'Admin Approved'),
                        ('rejected', 'Rejected'),
                        ('reinspection_requested', 'Reinspection Requested'),
                    ],
                    default='scheduled',
                    max_length=30,
                )),
                ('exterior_score', models.IntegerField(blank=True, null=True)),
                ('interior_score', models.IntegerField(blank=True, null=True)),
                ('engine_score', models.IntegerField(blank=True, null=True)),
                ('tyres_score', models.IntegerField(blank=True, null=True)),
                ('overall_score', models.IntegerField(blank=True, null=True)),
                ('condition_grade', models.CharField(blank=True, max_length=5)),
                ('inspector_notes', models.TextField(blank=True)),
                ('report_pdf', models.FileField(blank=True, null=True, upload_to='inspection_reports/')),
                ('admin_decision', models.CharField(blank=True, max_length=20)),
                ('admin_note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('lead', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='inspection_job',
                    to='crm.lead',
                )),
                ('vehicle', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='inspection_jobs',
                    to='vehicles.vehicle',
                )),
                ('inspector', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='inspection_jobs',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('assigned_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='jobs_assigned',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),

        # Create Bid
        migrations.CreateModel(
            name='Bid',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('is_winning', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('vehicle', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='bids',
                    to='vehicles.vehicle',
                )),
                ('dealer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='crm_bids',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-amount']},
        ),
    ]
