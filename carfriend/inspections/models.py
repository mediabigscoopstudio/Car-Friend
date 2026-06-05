from django.conf import settings
from django.db import models
from vehicles.models import Vehicle

SECTIONS = ["basic", "exterior", "interior", "engine", "tyres", "testdrive", "battery"]


class InspectionVisit(models.Model):
    class Status(models.TextChoices):
        SCHEDULED  = "scheduled",  "Scheduled"
        INPROGRESS = "inprogress", "In Progress"
        SUBMITTED  = "submitted",  "Submitted (awaiting Admin)"
        APPROVED   = "approved",   "Admin Approved"
        REJECTED   = "rejected",   "Rejected"
        REINSPECT  = "reinspect",  "Re-inspection requested"

    vehicle      = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="visits")
    inspector    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                     related_name="inspection_visits")
    scheduled_at = models.DateTimeField()
    status       = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self): return f"Visit · {self.vehicle} · {self.status}"


class InspectionReport(models.Model):
    visit            = models.OneToOneField(InspectionVisit, on_delete=models.CASCADE, related_name="report")
    checkpoints      = models.JSONField(default=dict, blank=True)
    score            = models.PositiveIntegerField(default=0)
    condition_grade  = models.CharField(max_length=1, blank=True)
    est_market_value = models.PositiveIntegerField(default=0)
    summary          = models.TextField(blank=True)
    pdf              = models.FileField(upload_to="inspections/reports/", blank=True, null=True)
    is_synced        = models.BooleanField(default=True)
    submitted_at     = models.DateTimeField(null=True, blank=True)
    decided_by       = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name="inspection_decisions")
    decision_note    = models.TextField(blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    def __str__(self): return f"Report · {self.visit.vehicle} · {self.score}/100"

    def compute_score(self):
        penalty = 0
        for section in self.checkpoints.values():
            for item in section.values():
                penalty += int(item.get("sev", 0)) * 2
        penalty += sum(d.severity for d in self.dents.all())
        self.score = max(0, 100 - penalty)
        self.condition_grade = (
            "A" if self.score >= 85 else
            "B" if self.score >= 70 else
            "C" if self.score >= 50 else "D"
        )
        return self.score


class DentMarker(models.Model):
    report   = models.ForeignKey(InspectionReport, on_delete=models.CASCADE, related_name="dents")
    x        = models.FloatField()
    y        = models.FloatField()
    label    = models.CharField(max_length=80, blank=True)
    severity = models.PositiveSmallIntegerField(default=1)

    def __str__(self): return f"Dent({self.x:.2f},{self.y:.2f}) sev{self.severity}"


class InspectionMedia(models.Model):
    class Kind(models.TextChoices):
        PHOTO = "photo", "Photo"
        VIDEO = "video", "Video"

    report      = models.ForeignKey(InspectionReport, on_delete=models.CASCADE, related_name="media")
    kind        = models.CharField(max_length=6, choices=Kind.choices, default=Kind.PHOTO)
    section     = models.CharField(max_length=40, blank=True)
    file        = models.FileField(upload_to="inspections/media/raw/")
    masked_file = models.ImageField(upload_to="inspections/media/masked/", blank=True, null=True)
    plate_masked = models.BooleanField(default=False)
    gps_lat     = models.FloatField(null=True, blank=True)
    gps_lng     = models.FloatField(null=True, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"{self.get_kind_display()} · {self.section}"
