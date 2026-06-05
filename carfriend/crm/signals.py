from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from notifications.services import notify
from .models import Task


@receiver(post_save, sender=Task)
def task_assigned_notify(sender, instance, created, **kwargs):
    if created:
        due_str = (
            f" · due {instance.due_at:%d %b %H:%M}" if instance.due_at else ""
        )
        notify(
            instance.assigned_to,
            "task_assigned",
            title=f"New task: {instance.title}",
            body=instance.get_kind_display() + due_str,
            url=f"http://teams.{settings.PARENT_HOST}:8000/tasks/",
        )
