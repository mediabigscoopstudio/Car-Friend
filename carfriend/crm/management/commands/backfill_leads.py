from django.core.management.base import BaseCommand
from vehicles.models import Vehicle
from crm.models import Lead


class Command(BaseCommand):
    help = 'Create missing Leads for all submitted/later-stage vehicles'

    def handle(self, *args, **options):
        eligible = Vehicle.objects.exclude(status='draft').exclude(status='rejected')
        created_count = 0
        skipped_count = 0

        for vehicle in eligible:
            lead, created = Lead.objects.get_or_create(
                vehicle=vehicle,
                defaults={'seller': vehicle.seller},
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f'  Created lead for {vehicle.plate_number} ({vehicle.display_name})'
                ))
            else:
                skipped_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone: {created_count} lead(s) created, {skipped_count} already existed.'
        ))
