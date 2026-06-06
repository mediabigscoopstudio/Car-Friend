from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_visit_leads(apps, schema_editor):
    InspectionVisit = apps.get_model('inspections', 'InspectionVisit')
    Lead = apps.get_model('crm', 'Lead')
    for visit in InspectionVisit.objects.all():
        try:
            lead = Lead.objects.get(vehicle=visit.vehicle)
            visit.lead = lead
            visit.save(update_fields=['lead'])
        except Lead.DoesNotExist:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0002_crm_v2'),
        ('inspections', '0002_inspectionmedia_mp4_file_inspectionmedia_slot_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='inspectionvisit',
            name='lead',
            field=models.OneToOneField(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='inspection_visit',
                to='crm.lead',
            ),
        ),
        migrations.AddField(
            model_name='inspectionvisit',
            name='assigned_by',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='visits_assigned',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='inspectionvisit',
            name='inspection_address',
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(backfill_visit_leads, migrations.RunPython.noop),
    ]
