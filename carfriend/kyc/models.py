from django.conf import settings
from django.db import models


class KYCVerification(models.Model):
    class Kind(models.TextChoices):
        AADHAAR = "aadhaar", "Aadhaar (OTP/e-Sign)"
        PAN     = "pan",     "PAN"
        GST     = "gst",     "GST + business docs"

    class Status(models.TextChoices):
        PENDING  = "pending",  "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    subject      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                     related_name="kyc_records")
    kind         = models.CharField(max_length=10, choices=Kind.choices)
    status       = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider_ref = models.CharField(max_length=120, blank=True)
    masked_value = models.CharField(max_length=40, blank=True)
    document     = models.FileField(upload_to="kyc/", blank=True, null=True)
    reviewed_by  = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="kyc_reviews")
    note         = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self): return f"{self.subject} · {self.get_kind_display()} · {self.status}"
