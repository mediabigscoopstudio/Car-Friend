from django.conf import settings
from django.db import models


class Ticket(models.Model):
    """A seller/dealer-raised support ticket. Staff triage happens in Django admin
    for now (a dedicated staff inbox is out of scope). The owner sees create / list /
    detail and can reply on the thread."""

    class Status(models.TextChoices):
        OPEN        = "open",        "Open"
        IN_PROGRESS = "in_progress", "In progress"
        RESOLVED    = "resolved",    "Resolved"

    class Category(models.TextChoices):
        SELLING    = "selling",    "Selling my car"
        KYC        = "kyc",        "KYC & verification"
        INSPECTION = "inspection", "Inspection"
        AUCTION    = "auction",    "Auction & offers"
        PAYMENT    = "payment",    "Payment & payout"
        OTHER      = "other",      "Something else"

    owner      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name="tickets")
    subject    = models.CharField(max_length=200)
    body       = models.TextField()
    category   = models.CharField(max_length=40, choices=Category.choices,
                                  default=Category.OTHER, blank=True)
    status     = models.CharField(max_length=20, choices=Status.choices,
                                  default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"#{self.pk} {self.subject}"


class TicketMessage(models.Model):
    """One message in a ticket thread (owner or staff)."""

    ticket     = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    author     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                   related_name="ticket_messages")
    body       = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"msg on #{self.ticket_id}"
