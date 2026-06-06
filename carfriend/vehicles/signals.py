from django.db.models.signals import post_save
from django.dispatch import receiver
from vehicles.models import Vehicle


@receiver(post_save, sender=Vehicle)
def create_lead_on_submit(sender, instance, created, **kwargs):
    if created and instance.status == Vehicle.STATUS_SUBMITTED:
        from crm.models import Lead
        Lead.objects.get_or_create(
            vehicle=instance,
            defaults={'seller': instance.seller},
        )
