from django.conf import settings
from django.db import models
from vehicles.models import Vehicle


class Lead(models.Model):
    class Stage(models.TextChoices):
        NEW          = "new",          "New"
        QUALIFIED    = "qualified",    "Qualified"
        INSP_SCHED   = "insp_sched",   "Inspection Scheduled"
        ADMIN_OK     = "admin_ok",     "Admin Approved"
        NEGOTIATION  = "negotiation",  "Negotiation"
        AUCTION_MADE = "auction_made", "Auction Created"
        CLOSED       = "closed",       "Closed"

    seller         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                       related_name="leads")
    vehicle        = models.ForeignKey(Vehicle, null=True, blank=True, on_delete=models.SET_NULL)
    source         = models.CharField(max_length=60, blank=True)
    stage          = models.CharField(max_length=14, choices=Stage.choices, default=Stage.NEW)
    assigned_to    = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                       on_delete=models.SET_NULL, related_name="assigned_leads")
    expected_price = models.PositiveIntegerField(default=0)
    status         = models.CharField(max_length=20, default="Enabled")
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self): return f"Lead · {self.seller} · {self.get_stage_display()}"


class NegotiationOffer(models.Model):
    class Result(models.TextChoices):
        PENDING   = "pending",   "Pending"
        ACCEPTED  = "accepted",  "Accepted"
        REJECTED  = "rejected",  "Rejected"
        COUNTERED = "countered", "Countered"

    lead          = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="offers")
    offer_price   = models.PositiveIntegerField()
    by            = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    result        = models.CharField(max_length=10, choices=Result.choices, default=Result.PENDING)
    counter_price = models.PositiveIntegerField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Offer ₹{self.offer_price:,} · {self.result}"


class CommunicationLog(models.Model):
    class Kind(models.TextChoices):
        CALL     = "call",     "Call"
        NOTE     = "note",     "Note"
        COUNTER  = "counter",  "Counter offer"
        INTEREST = "interest", "Interest level"

    lead       = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.CASCADE,
                                   related_name="comms")
    dealer     = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.CASCADE, related_name="dealer_comms")
    vehicle    = models.ForeignKey(Vehicle, null=True, blank=True, on_delete=models.SET_NULL)
    kind       = models.CharField(max_length=10, choices=Kind.choices, default=Kind.NOTE)
    body       = models.TextField()
    by         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                   related_name="comms_made")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self): return f"{self.get_kind_display()} · {self.created_at:%d %b %H:%M}"


class Task(models.Model):
    class Kind(models.TextChoices):
        CALL        = "call",        "Call reminder"
        FOLLOWUP    = "followup",    "Follow-up"
        NEGOTIATION = "negotiation", "Negotiation note"
        DOC         = "doc",         "Pending document"

    class Status(models.TextChoices):
        OPEN    = "open",    "Open"
        DONE    = "done",    "Done"
        OVERDUE = "overdue", "Overdue"

    title       = models.CharField(max_length=200)
    kind        = models.CharField(max_length=12, choices=Kind.choices, default=Kind.FOLLOWUP)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name="tasks")
    lead        = models.ForeignKey(Lead, null=True, blank=True, on_delete=models.SET_NULL)
    due_at      = models.DateTimeField(null=True, blank=True)
    status      = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    notes       = models.TextField(blank=True)
    created_by  = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                    related_name="tasks_created")
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_at", "-created_at"]

    def __str__(self): return f"{self.get_kind_display()} · {self.title} · {self.status}"
