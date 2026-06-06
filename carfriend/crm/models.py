from django.db import models
from django.conf import settings
from vehicles.models import Vehicle


class Lead(models.Model):

    STAGE_NEW         = 'new'
    STAGE_QUALIFIED   = 'qualified'
    STAGE_INSP_SCHED  = 'inspection_scheduled'
    STAGE_INSP_DONE   = 'inspection_done'
    STAGE_APPROVED    = 'admin_approved'
    STAGE_NEGOTIATION = 'negotiation'
    STAGE_AUCTION     = 'auction_created'
    STAGE_CLOSED      = 'closed'

    STAGE_CHOICES = [
        (STAGE_NEW,         'New'),
        (STAGE_QUALIFIED,   'Qualified'),
        (STAGE_INSP_SCHED,  'Inspection Scheduled'),
        (STAGE_INSP_DONE,   'Inspection Done'),
        (STAGE_APPROVED,    'Admin Approved'),
        (STAGE_NEGOTIATION, 'Negotiation'),
        (STAGE_AUCTION,     'Auction Created'),
        (STAGE_CLOSED,      'Closed'),
    ]

    vehicle     = models.OneToOneField(Vehicle, on_delete=models.CASCADE, related_name='lead')
    seller      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name='leads')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='assigned_leads')
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
