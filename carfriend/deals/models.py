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
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    def __str__(self): return f"Deal · {self.vehicle} · {self.status}"

    @property
    def margin(self):
        return self.final_price - self.seller_shown_price


class DealAgreement(models.Model):
    deal             = models.OneToOneField(Deal, on_delete=models.CASCADE, related_name="agreement")
    pdf              = models.FileField(upload_to="deals/agreements/", blank=True, null=True)
    seller_esign_ref = models.CharField(max_length=120, blank=True)
    dealer_esign_ref = models.CharField(max_length=120, blank=True)
    seller_signed    = models.BooleanField(default=False)
    dealer_signed    = models.BooleanField(default=False)
    created_at       = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Agreement · {self.deal}"
