import random
from django.core.management.base import BaseCommand
from crm.models import Lead


class Command(BaseCommand):
    help = "Distribute existing leads across all stages for a realistic demo board."

    def handle(self, *args, **kwargs):
        stages = [s for s, _ in Lead.Stage.choices]
        for lead in Lead.objects.all():
            lead.stage = random.choice(stages)
            lead.save(update_fields=["stage"])
        self.stdout.write(self.style.SUCCESS("Spread leads across stages."))
