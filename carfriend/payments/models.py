from django.conf import settings
from django.db import models
from deals.models import Deal


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING   = "pending",   "Pending"
        CONFIRMED = "confirmed", "Confirmed"

    deal         = models.ForeignKey(Deal, on_delete=models.CASCADE, related_name="payments")
    amount       = models.PositiveIntegerField()
    status       = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    proof_image  = models.ImageField(upload_to="payments/proofs/", blank=True, null=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="payments_confirmed")
    confirmed_at = models.DateTimeField(null=True, blank=True)
    note         = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self): return f"₹{self.amount:,} · {self.status} · {self.deal}"
