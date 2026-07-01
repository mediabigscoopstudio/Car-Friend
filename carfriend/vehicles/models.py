from django.db import models
from accounts.models import User


class Vehicle(models.Model):

    STATUS_DRAFT      = 'draft'
    STATUS_SUBMITTED  = 'submitted'
    STATUS_INSPECTION = 'inspection_scheduled'
    STATUS_INSPECTED  = 'inspection_done'
    STATUS_APPROVED   = 'approved'
    STATUS_AUCTION    = 'in_auction'
    STATUS_SOLD       = 'sold'
    STATUS_REJECTED   = 'rejected'

    STATUS_CHOICES = [
        (STATUS_DRAFT,      'Draft'),
        (STATUS_SUBMITTED,  'Submitted'),
        (STATUS_INSPECTION, 'Inspection Scheduled'),
        (STATUS_INSPECTED,  'Inspection Done'),
        (STATUS_APPROVED,   'Admin Approved'),
        (STATUS_AUCTION,    'In Auction'),
        (STATUS_SOLD,       'Sold'),
        (STATUS_REJECTED,   'Rejected'),
    ]

    FUEL_PETROL   = 'petrol'
    FUEL_DIESEL   = 'diesel'
    FUEL_CNG      = 'cng'
    FUEL_ELECTRIC = 'electric'
    FUEL_HYBRID   = 'hybrid'

    FUEL_CHOICES = [
        (FUEL_PETROL,   'Petrol'),
        (FUEL_DIESEL,   'Diesel'),
        (FUEL_CNG,      'CNG'),
        (FUEL_ELECTRIC, 'Electric'),
        (FUEL_HYBRID,   'Hybrid'),
    ]

    TRANSMISSION_MANUAL    = 'manual'
    TRANSMISSION_AUTOMATIC = 'automatic'

    TRANSMISSION_CHOICES = [
        (TRANSMISSION_MANUAL,    'Manual'),
        (TRANSMISSION_AUTOMATIC, 'Automatic'),
    ]

    # Owner / seller
    seller          = models.ForeignKey(User, on_delete=models.CASCADE, related_name='vehicles')

    # From Vahaan / plate lookup
    plate_number    = models.CharField(max_length=20, unique=True)
    make            = models.CharField(max_length=100)
    model           = models.CharField(max_length=100)
    variant         = models.CharField(max_length=100, blank=True)
    year            = models.IntegerField()
    fuel_type       = models.CharField(max_length=20, choices=FUEL_CHOICES)
    transmission    = models.CharField(max_length=20, choices=TRANSMISSION_CHOICES)
    colour          = models.CharField(max_length=100)
    registration_date = models.DateField(null=True, blank=True)
    registration_state = models.CharField(max_length=100, blank=True)
    rto             = models.CharField(max_length=100, blank=True)
    owner_name      = models.CharField(max_length=200, blank=True)
    owner_number    = models.IntegerField(default=1)
    chassis_number  = models.CharField(max_length=100, blank=True)
    engine_number   = models.CharField(max_length=100, blank=True)
    insurance_valid_till = models.DateField(null=True, blank=True)
    is_hypothecated = models.BooleanField(default=False)
    accident_history = models.BooleanField(default=False)

    # Seller fills
    odometer_km     = models.IntegerField(null=True, blank=True)
    last_service_date = models.DateField(null=True, blank=True)
    tyre_condition  = models.CharField(max_length=100, blank=True)
    expected_price  = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Location
    city            = models.CharField(max_length=100, blank=True)
    inspection_address = models.TextField(blank=True)
    preferred_inspection_slot = models.CharField(max_length=200, blank=True)

    # Documents (file uploads)
    rc_document     = models.FileField(upload_to='vehicles/docs/', null=True, blank=True)
    insurance_document = models.FileField(upload_to='vehicles/docs/', null=True, blank=True)
    service_history = models.FileField(upload_to='vehicles/docs/', null=True, blank=True)
    noc_document    = models.FileField(upload_to='vehicles/docs/', null=True, blank=True)

    # Status and flags
    status          = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    inspection_report_ready = models.BooleanField(default=False)
    auction_active  = models.BooleanField(default=False)
    # Denormalised from the inspection report on submit (read by seller dashboard
    # + auction room). Single-letter grade A/B/C/D, matching report.condition_grade.
    condition_grade = models.CharField(max_length=1, blank=True)
    # Auction vs scrap — mirrored from InspectionReport.disposition on submit.
    # SCRAP cars are excluded from auction creation / listings.
    DISPOSITION_CHOICES = [("auction", "Auction"), ("scrap", "Scrap")]
    disposition     = models.CharField(max_length=10, choices=DISPOSITION_CHOICES, blank=True, default="")

    # Timestamps
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.year} {self.make} {self.model} — {self.plate_number}"

    @property
    def display_name(self):
        return f"{self.make} {self.model} {self.variant}".strip()

    @property
    def status_label(self):
        return dict(self.STATUS_CHOICES).get(self.status, self.status)
