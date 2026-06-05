from django.core.management.base import BaseCommand
from django.utils import timezone

from crm.models import Task
from notifications.services import notify


class Command(BaseCommand):
    help = "Flag overdue tasks and notify assignees."

    def handle(self, *a, **k):
        now = timezone.now()
        due = Task.objects.filter(status="open", due_at__lte=now)
        count = due.count()
        for t in due:
            t.status = "overdue"
            t.save(update_fields=["status"])
            notify(t.assigned_to, "task_due", title=f"Task due: {t.title}",
                   body=t.get_kind_display())
        self.stdout.write(self.style.SUCCESS(f"{count} task(s) flagged overdue."))
