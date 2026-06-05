from django.conf import settings
from django.db import models


class Vehicle(models.Model):
    class Grade(models.TextChoices):
        A = "A", "A (Excellent)"
        B = "B", "B (Good)"
        C = "C", "C (Fair)"
        D = "D", "D (Poor)"

    class Status(models.TextChoices):
        DRAFT      = "draft",      "Draft"
        INSPECTING = "inspecting", "Inspection in progress"
        APPROVED   = "approved",   "Inspection approved"
        LISTED     = "listed",     "Listed / auction"
        SOLD       = "sold",       "Sold"

    seller           = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                         related_name="vehicles")
    make             = models.CharField(max_length=60)
    model            = models.CharField(max_length=80)
    variant          = models.CharField(max_length=80, blank=True)
    year             = models.PositiveIntegerField()
    reg_number       = models.CharField(max_length=20, blank=True)
    ownership        = models.CharField(max_length=40, blank=True)
    location         = models.CharField(max_length=120, blank=True)
    expected_price   = models.PositiveIntegerField(default=0)
    condition_grade  = models.CharField(max_length=1, choices=Grade.choices, blank=True)
    est_market_value = models.PositiveIntegerField(default=0)
    status           = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self): return f"{self.make} {self.model} {self.variant} ({self.year})"

    @property
    def title(self): return f"{self.make} {self.model} {self.variant}".strip()


class VehiclePhoto(models.Model):
    vehicle      = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="photos")
    image        = models.ImageField(upload_to="vehicles/photos/")
    section      = models.CharField(max_length=40, blank=True)
    plate_masked = models.BooleanField(default=False)
    gps_lat      = models.FloatField(null=True, blank=True)
    gps_lng      = models.FloatField(null=True, blank=True)
    captured_at  = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"Photo · {self.vehicle} · {self.section}"


class VehicleDocument(models.Model):
    class Kind(models.TextChoices):
        RC        = "rc",        "RC"
        INSURANCE = "insurance", "Insurance"
        SERVICE   = "service",   "Service history"

    vehicle    = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="documents")
    kind       = models.CharField(max_length=12, choices=Kind.choices)
    file       = models.FileField(upload_to="vehicles/docs/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"{self.get_kind_display()} · {self.vehicle}"
