from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import InspectionVisit


@receiver(post_save, sender=InspectionVisit)
def sync_crm_lead_on_visit_change(sender, instance, **kwargs):
    """Keep crm.Lead stage in sync when inspector submits/gets approved.
    Routed through the single transition entrypoint so every move is audited."""
    if not instance.lead_id:
        return
    try:
        from crm.services import transition_lead
        lead = instance.lead
        if instance.status == InspectionVisit.Status.INPROGRESS:
            transition_lead(lead, "inspection_started")
        elif instance.status == InspectionVisit.Status.SUBMITTED:
            transition_lead(lead, "report_submitted")
        elif instance.status == InspectionVisit.Status.APPROVED:
            transition_lead(lead, "admin_approved")
    except Exception:
        pass
