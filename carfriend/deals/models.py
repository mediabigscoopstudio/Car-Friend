from django.conf import settings
from django.db import models
from vehicles.models import Vehicle


class Deal(models.Model):
    class Status(models.TextChoices):
        OPEN      = "open",      "Open"
        AGREEMENT = "agreement", "Agreement pending"
        SIGNED    = "signed",    "Signed"
        PAID      = "paid",      "Payment confirmed"
        CLOSED    = "closed",    "Closed"

    vehicle            = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="deals")
    seller             = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                           related_name="deals_as_seller")
    dealer             = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                           related_name="deals_as_dealer")
    final_price        = models.PositiveIntegerField()
    seller_shown_price = models.PositiveIntegerField(default=0)
    status             = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    assigned_sales     = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                           on_delete=models.SET_NULL, related_name="deals_assigned")
    # Finalization breakdown (set on closure)
    gst_percentage     = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    gst_amount         = models.PositiveIntegerField(default=0)
    additional_charges = models.JSONField(default=list, blank=True)   # [{"label": str, "amount": int}, ...]
    cf_commission      = models.PositiveIntegerField(default=0)
    grand_total        = models.PositiveIntegerField(default=0)
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    def __str__(self): return f"Deal · {self.vehicle} · {self.status}"

    @property
    def margin(self):
        return self.final_price - self.seller_shown_price

    @property
    def additional_charges_total(self):
        try:
            return sum(int(c.get("amount", 0)) for c in (self.additional_charges or []))
        except (TypeError, ValueError, AttributeError):
            return 0


class DealAgreement(models.Model):
    deal             = models.OneToOneField(Deal, on_delete=models.CASCADE, related_name="agreement")
    pdf              = models.FileField(upload_to="deals/agreements/", blank=True, null=True)
    seller_esign_ref = models.CharField(max_length=120, blank=True)
    dealer_esign_ref = models.CharField(max_length=120, blank=True)
    seller_signed    = models.BooleanField(default=False)
    dealer_signed    = models.BooleanField(default=False)
    seller_signed_at = models.DateTimeField(null=True, blank=True)
    dealer_signed_at = models.DateTimeField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Agreement · {self.deal}"

    @property
    def fully_signed(self):
        return self.seller_signed and self.dealer_signed


class HandoverChecklist(models.Model):
    """Procurement Associate handover checklist for a closed/paid deal."""

    deal                     = models.OneToOneField(Deal, on_delete=models.CASCADE, related_name="handover")
    keys_received            = models.BooleanField(default=False)
    rc_received              = models.BooleanField(default=False)
    insurance_received       = models.BooleanField(default=False)
    service_history_received = models.BooleanField(default=False)
    notes                    = models.TextField(blank=True)
    stock_out_at             = models.DateTimeField(null=True, blank=True)
    completed_by             = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                                 on_delete=models.SET_NULL, related_name="handovers_completed")
    created_at               = models.DateTimeField(auto_now_add=True)
    updated_at               = models.DateTimeField(auto_now=True)

    def __str__(self): return f"Handover · {self.deal}"

    @property
    def all_received(self):
        return all([self.keys_received, self.rc_received,
                    self.insurance_received, self.service_history_received])

    @property
    def is_stocked_out(self):
        return self.stock_out_at is not None
