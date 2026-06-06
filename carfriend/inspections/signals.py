from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import InspectionVisit


@receiver(post_save, sender=InspectionVisit)
def sync_crm_lead_on_visit_change(sender, instance, **kwargs):
    """Keep crm.Lead stage in sync when inspector submits/gets approved."""
    if not instance.lead_id:
        return
    try:
        from crm.models import Lead
        lead = instance.lead
        if instance.status == InspectionVisit.Status.SUBMITTED:
            if lead.stage != Lead.STAGE_INSP_DONE:
                lead.stage = Lead.STAGE_INSP_DONE
                lead.save(update_fields=['stage'])
        elif instance.status == InspectionVisit.Status.APPROVED:
            if lead.stage != Lead.STAGE_APPROVED:
                lead.stage = Lead.STAGE_APPROVED
                lead.save(update_fields=['stage'])
    except Exception:
        pass
