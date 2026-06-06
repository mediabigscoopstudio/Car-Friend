"""
Backfill InspectionVisit records for any InspectionJob that lacks one.
Run once after deploying the assign-visit fix:

    python manage.py backfill_visits
"""

from django.core.management.base import BaseCommand
from crm.models import InspectionJob
from inspections.models import InspectionVisit


class Command(BaseCommand):
    help = "Create missing InspectionVisit records for existing InspectionJobs"

    def handle(self, *args, **options):
        created = 0
        skipped = 0
        for job in InspectionJob.objects.select_related('vehicle', 'inspector'):
            if not job.inspector:
                skipped += 1
                continue
            visit, new = InspectionVisit.objects.get_or_create(
                vehicle=job.vehicle,
                defaults={
                    'inspector':    job.inspector,
                    'scheduled_at': job.scheduled_at,
                    'status':       InspectionVisit.Status.SCHEDULED,
                }
            )
            if new:
                created += 1
                self.stdout.write(f"  Created visit for {job.vehicle} → {job.inspector.get_full_name() or job.inspector.email}")
            else:
                skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {created} InspectionVisit(s), skipped {skipped}."
        ))
