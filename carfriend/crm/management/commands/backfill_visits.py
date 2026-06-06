"""
Sync InspectionVisit records with InspectionJob assignments.
Creates missing visits AND corrects the inspector/schedule on existing ones.

    python manage.py backfill_visits
"""

from django.core.management.base import BaseCommand
from crm.models import InspectionJob
from inspections.models import InspectionVisit


class Command(BaseCommand):
    help = "Create/fix InspectionVisit records for all InspectionJobs"

    def handle(self, *args, **options):
        created = updated = skipped = 0

        for job in InspectionJob.objects.select_related('vehicle', 'inspector'):
            if not job.inspector:
                self.stdout.write(f"  SKIP (no inspector): {job.vehicle}")
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
                self.stdout.write(
                    f"  CREATED visit for {job.vehicle} → {job.inspector.get_full_name() or job.inspector.email}"
                )
            else:
                # Fix inspector/schedule if they don't match the job
                changed = False
                if visit.inspector_id != job.inspector_id:
                    visit.inspector = job.inspector
                    changed = True
                if visit.scheduled_at != job.scheduled_at:
                    visit.scheduled_at = job.scheduled_at
                    changed = True
                if visit.status not in (InspectionVisit.Status.SUBMITTED, InspectionVisit.Status.APPROVED):
                    if visit.status != InspectionVisit.Status.SCHEDULED:
                        visit.status = InspectionVisit.Status.SCHEDULED
                        changed = True

                if changed:
                    visit.save()
                    updated += 1
                    self.stdout.write(
                        f"  UPDATED visit #{visit.id} for {job.vehicle} → "
                        f"{job.inspector.get_full_name() or job.inspector.email}"
                    )
                else:
                    skipped += 1
                    self.stdout.write(f"  OK (already correct): {job.vehicle}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created {created}, updated {updated}, skipped {skipped}."
        ))
