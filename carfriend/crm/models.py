from django.db import models
from django.conf import settings
from vehicles.models import Vehicle


class Lead(models.Model):

    STAGE_NEW         = 'new'
    STAGE_QUALIFIED   = 'qualified'
    STAGE_UNQUALIFIED = 'unqualified'
    STAGE_INSP_SCHED  = 'inspection_scheduled'
    STAGE_INSP_PROG   = 'inspection_in_progress'
    STAGE_INSP_DONE   = 'inspection_done'
    STAGE_APPROVED    = 'admin_approved'
    STAGE_ASSIGNED    = 'assigned'
    STAGE_NEGOTIATION = 'negotiation'
    STAGE_AUCTION     = 'auction_created'
    STAGE_AUCTION_LIVE   = 'auction_live'
    STAGE_AUCTION_CLOSED = 'auction_closed'
    STAGE_SELLER_APPROVED = 'seller_approved'
    STAGE_OCB         = 'ocb_in_progress'
    STAGE_AGREEMENT   = 'agreement_signed'
    STAGE_PROCUREMENT = 'handed_to_procurement'
    STAGE_CLOSED      = 'closed'

    STAGE_CHOICES = [
        (STAGE_NEW,            'New'),
        (STAGE_QUALIFIED,      'Qualified'),
        (STAGE_UNQUALIFIED,    'Un-Qualified'),
        (STAGE_INSP_SCHED,     'Inspection Scheduled'),
        (STAGE_INSP_PROG,      'Inspection In Progress'),
        (STAGE_INSP_DONE,      'Report Submitted'),
        (STAGE_APPROVED,       'Admin Approved'),
        (STAGE_ASSIGNED,       'Assigned'),
        (STAGE_NEGOTIATION,    'Negotiation'),
        (STAGE_AUCTION,        'Auction Created'),
        (STAGE_AUCTION_LIVE,   'Auction Live'),
        (STAGE_AUCTION_CLOSED, 'Auction Closed'),
        (STAGE_SELLER_APPROVED,'Seller Approved'),
        (STAGE_OCB,            'OCB In Progress'),
        (STAGE_AGREEMENT,      'Agreement Signed'),
        (STAGE_PROCUREMENT,    'Handed To Procurement'),
        (STAGE_CLOSED,         'Closed'),
    ]

    vehicle     = models.OneToOneField(Vehicle, on_delete=models.CASCADE, related_name='lead')
    seller      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='leads')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='assigned_leads')
    # The retail associate a Retail Head allocates this approved lead to. Kept
    # distinct from `assigned_to`, which the Lead Manager sets to themselves at
    # intake/qualification.
    assigned_associate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                            null=True, blank=True, related_name='allocated_leads')
    allocated_at = models.DateTimeField(null=True, blank=True)
    allocated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='leads_allocated_by_me')
    stage       = models.CharField(max_length=30, choices=STAGE_CHOICES, default=STAGE_NEW)
    notes       = models.TextField(blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Lead: {self.vehicle} — {self.get_stage_display()}"

    @property
    def stage_label(self):
        return dict(self.STAGE_CHOICES).get(self.stage, self.stage)


class Bid(models.Model):
    vehicle    = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name='bids')
    dealer     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='crm_bids')
    amount     = models.DecimalField(max_digits=12, decimal_places=2)
    is_winning = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-amount']

    def __str__(self):
        return f"₹{self.amount} on {self.vehicle} by {self.dealer.email}"


class Task(models.Model):
    """Internal task (created by Retail; assigned to Sales/Procurement etc.)."""

    class Status(models.TextChoices):
        TODO        = "todo",        "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
        DONE        = "done",        "Done"
        CANCELLED   = "cancelled",   "Cancelled"

    class Priority(models.TextChoices):
        LOW    = "low",    "Low"
        MEDIUM = "medium", "Medium"
        HIGH   = "high",   "High"

    title        = models.CharField(max_length=255)
    description  = models.TextField(blank=True)
    created_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                     related_name="created_tasks")
    assigned_to  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                     related_name="assigned_tasks")
    status       = models.CharField(max_length=12, choices=Status.choices, default=Status.TODO)
    priority     = models.CharField(max_length=6, choices=Priority.choices, default=Priority.MEDIUM)
    due_date     = models.DateField(null=True, blank=True)
    related_lead = models.ForeignKey("crm.Lead", null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="tasks")
    related_ocb  = models.ForeignKey("auctions.OCBListing", null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="tasks")
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        from django.utils import timezone
        return bool(self.due_date and self.status not in (self.Status.DONE, self.Status.CANCELLED)
                    and self.due_date < timezone.localdate())


class TaskNote(models.Model):
    """A note on a Task. The assigned Sales Associate (or any participant) can
    add notes; status stays Retail-controlled. Authors may edit their own notes."""

    task       = models.ForeignKey("crm.Task", on_delete=models.CASCADE, related_name="notes")
    author     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name="task_notes")
    note       = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"note by {self.author} on task {self.task_id}"


class LeadNote(models.Model):
    """A call note / activity-log entry logged by the Retail Associate on a lead."""

    lead       = models.ForeignKey("crm.Lead", on_delete=models.CASCADE, related_name="call_notes")
    author     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name="lead_notes")
    note       = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"note by {self.author} on lead {self.lead_id}"


class LeadAllocation(models.Model):
    """Audit row written every time a Retail Head allocates / re-allocates a
    lead to a retail associate (assumption D — every re-allocation is logged)."""

    lead           = models.ForeignKey("crm.Lead", on_delete=models.CASCADE, related_name="allocations")
    from_associate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name="lead_allocations_from")
    to_associate   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name="lead_allocations_to")
    by             = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name="lead_allocations_by")
    at             = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self):
        return f"alloc lead {self.lead_id} → {self.to_associate}"


class DealerAllocation(models.Model):
    """Audit row written every time a Sales Head allocates / re-allocates a
    dealer to a sales associate (assumption D — every re-allocation is logged)."""

    dealer         = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                       related_name="dealer_allocations")
    from_associate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name="dealer_allocations_from")
    to_associate   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name="dealer_allocations_to")
    by             = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name="dealer_allocations_by")
    at             = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self):
        return f"alloc dealer {self.dealer_id} → {self.to_associate}"


class LeadStatusEvent(models.Model):
    """Immutable audit trail of automatic (and override) pipeline transitions.
    Written only by crm.services.transition_lead — the single source of truth."""

    lead        = models.ForeignKey("crm.Lead", on_delete=models.CASCADE, related_name="status_events")
    from_status = models.CharField(max_length=30, blank=True)
    to_status   = models.CharField(max_length=30)
    trigger     = models.CharField(max_length=40)
    actor       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="lead_status_events")
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"lead {self.lead_id}: {self.from_status or '∅'} → {self.to_status} ({self.trigger})"
