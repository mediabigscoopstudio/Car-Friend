from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0002_crm_v2'),
        ('inspections', '0003_inspectionvisit_lead_assigned_by_address'),
    ]

    operations = [
        migrations.DeleteModel(name='InspectionJob'),
    ]
