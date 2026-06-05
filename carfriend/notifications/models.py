from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Channel(models.TextChoices):
        INAPP    = "inapp",    "In-app"
        PUSH     = "push",     "Push (FCM)"
        WHATSAPP = "whatsapp", "WhatsApp"
        SMS      = "sms",      "SMS"

    class Event(models.TextChoices):
        TASK_ASSIGNED  = "task_assigned",  "Task assigned"
        TASK_DUE       = "task_due",       "Task due"
        AUCTION_START  = "auction_start",  "Auction started"
        BID_UPDATE     = "bid_update",     "Bid update"
        DEAL_CONFIRMED = "deal_confirmed", "Deal confirmed"
        DOC_PENDING    = "doc_pending",    "Document pending"
        INSP_ASSIGNED  = "insp_assigned",  "Inspection assigned"
        INSP_DECISION  = "insp_decision",  "Inspection approved/rejected"
        KYC_RESULT     = "kyc_result",     "KYC result"
        PAYMENT_OK     = "payment_ok",     "Payment confirmed"

    recipient  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name="notifications")
    event      = models.CharField(max_length=20, choices=Event.choices)
    channels   = models.JSONField(default=list)
    title      = models.CharField(max_length=160)
    body       = models.TextField(blank=True)
    url        = models.CharField(max_length=300, blank=True)
    is_read    = models.BooleanField(default=False)
    delivered  = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self): return f"{self.get_event_display()} → {self.recipient}"
