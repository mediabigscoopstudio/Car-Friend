# CRM signals.
# - auto-lead creation from a submitted Vehicle lives in vehicles/signals.py
#   (the public sell-flow; not touched here).
# - here we notify Lead Managers when a new lead arrives.

from django.db.models.signals import post_save
from django.dispatch import receiver

from crm.models import Lead


@receiver(post_save, sender=Lead)
def notify_lead_managers_on_new_lead(sender, instance, created, **kwargs):
    if not created:
        return
    # Imported lazily to avoid app-load import cycles.
    from accounts.models import Role, User
    from notifications.services import notify

    for lm in User.objects.filter(role=Role.LEAD_MANAGER, is_suspended=False):
        try:
            notify(lm, "task_assigned",
                   title="New lead to review",
                   body=f"{instance.vehicle} — qualify and book an inspection.",
                   url="/lead-manager/")
        except Exception:
            pass
