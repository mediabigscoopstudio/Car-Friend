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
    class Decision(models.TextChoices):
        PENDING  = "pending",  "Awaiting admin"
        APPROVED = "approved", "Approved"
        REDO     = "redo",     "Redo requested"
        REMOVED  = "removed",  "Removed / voided"

    visit            = models.OneToOneField("InspectionVisit", on_delete=models.CASCADE, related_name="report")
    checkpoints      = models.JSONField(default=dict, blank=True)
    photos           = models.JSONField(default=dict, blank=True)
    comments         = models.JSONField(default=list, blank=True)
    score            = models.PositiveIntegerField(default=0)
    condition_grade  = models.CharField(max_length=1, blank=True)
    est_market_value = models.PositiveIntegerField(default=0)
    decision         = models.CharField(max_length=10, choices=Decision.choices, default=Decision.PENDING)
    is_locked        = models.BooleanField(default=False)
    redo_count       = models.PositiveSmallIntegerField(default=0)
    decision_note    = models.TextField(blank=True)
    decided_by       = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                         on_delete=models.SET_NULL, related_name="inspection_decisions")
    pdf              = models.FileField(upload_to="inspections/reports/", blank=True, null=True)
    submitted_at     = models.DateTimeField(null=True, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    def __str__(self): return f"Report · {self.visit.vehicle} · {self.score}/100"

    @property
    def editable(self):
        return not self.is_locked

    def compute_score(self):
        penalty = 0
        for sec_data in self.checkpoints.values():
            if not isinstance(sec_data, dict):
                continue
            for part_data in sec_data.values():
                if not isinstance(part_data, dict):
                    continue
                # part_data is {subpart_or_underscore: {status, condition, value}}
                for cell in part_data.values():
                    if isinstance(cell, dict) and cell.get("status") == "issue":
                        penalty += 4
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
        AUDIO = "audio", "Audio"

    report       = models.ForeignKey(InspectionReport, on_delete=models.CASCADE, related_name="media")
    kind         = models.CharField(max_length=6, choices=Kind.choices, default=Kind.PHOTO)
    slot         = models.CharField(max_length=80, blank=True)
    section      = models.CharField(max_length=40, blank=True)
    file         = models.FileField(upload_to="inspections/media/raw/", blank=True, null=True)
    webp_file    = models.ImageField(upload_to="inspections/media/webp/", blank=True, null=True)
    mp4_file     = models.FileField(upload_to="inspections/media/mp4/", blank=True, null=True)
    masked_file  = models.ImageField(upload_to="inspections/media/masked/", blank=True, null=True)
    plate_masked = models.BooleanField(default=False)
    gps_lat      = models.FloatField(null=True, blank=True)
    gps_lng      = models.FloatField(null=True, blank=True)
    captured_at  = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    @property
    def image(self):
        return self.webp_file or self.masked_file or (self.file if self.kind == self.Kind.PHOTO else None)

    def __str__(self): return f"{self.get_kind_display()} · {self.slot or self.section}"
