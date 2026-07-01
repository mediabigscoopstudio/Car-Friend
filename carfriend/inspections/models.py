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

    lead               = models.OneToOneField(
                             'crm.Lead', on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='inspection_visit')
    vehicle            = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="visits")
    inspector          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                           related_name="inspection_visits")
    assigned_by        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                           blank=True, related_name="visits_assigned")
    scheduled_at       = models.DateTimeField()
    inspection_address = models.TextField(blank=True)
    status             = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED)
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self): return f"Visit · {self.vehicle} · {self.status}"


class InspectionReport(models.Model):
    class Decision(models.TextChoices):
        PENDING  = "pending",  "Awaiting admin"
        APPROVED = "approved", "Approved"
        REDO     = "redo",     "Redo requested"
        REMOVED  = "removed",  "Removed / voided"

    class Disposition(models.TextChoices):
        AUCTION = "auction", "Auction"
        SCRAP   = "scrap",   "Scrap"

    class ExhaustSmoke(models.TextChoices):
        WHITE = "white", "White"
        BLACK = "black", "Black"
        NONE  = "none",  "No Smoke"

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
    # Challan / traffic-violation snapshot, fetched from Surepass at submit time.
    challan_data          = models.JSONField(null=True, blank=True)   # normalized list of challans
    challan_total_pending = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    challan_count         = models.IntegerField(default=0)
    challan_fetched_at    = models.DateTimeField(null=True, blank=True)
    challan_fetch_status  = models.CharField(max_length=10, blank=True, default="")  # ok / failed / no_data
    # Pre-inspection hero shot (3/4 front angle) — captured before the zones.
    auction_hero_image = models.ImageField(upload_to="inspections/hero/", max_length=255, blank=True, null=True)
    # Wrap-up section (replaces the old 360 set & sign-off).
    front_photo      = models.ImageField(upload_to="inspections/wrapup/", max_length=255, blank=True, null=True)
    rear_photo       = models.ImageField(upload_to="inspections/wrapup/", max_length=255, blank=True, null=True)
    left_photo       = models.ImageField(upload_to="inspections/wrapup/", max_length=255, blank=True, null=True)
    right_photo      = models.ImageField(upload_to="inspections/wrapup/", max_length=255, blank=True, null=True)
    walkaround_video = models.FileField(upload_to="inspections/wrapup/video/", max_length=255, blank=True, null=True)
    engine_audio     = models.FileField(upload_to="inspections/wrapup/audio/", max_length=255, blank=True, null=True)
    final_notes      = models.TextField(blank=True, default="")
    # Insurance (Details zone) — structured, replaces the OK/Issue checkpoint.
    insurance_type         = models.CharField(max_length=30, blank=True)
    insurer_name           = models.CharField(max_length=120, blank=True)
    policy_number          = models.CharField(max_length=80, blank=True)
    insurance_expiry_month = models.CharField(max_length=12, blank=True)
    insurance_expiry_year  = models.CharField(max_length=4, blank=True)
    insurance_photo        = models.ImageField(upload_to="inspections/insurance/", max_length=255, blank=True, null=True)
    # ── Disposition (auction vs scrap): chosen at the hero step, required before
    # the walk proceeds; mirrored to Vehicle.disposition on submit. ──
    disposition   = models.CharField(max_length=10, choices=Disposition.choices, blank=True, default="")
    # Engine exhaust smoke — auction/full inspection only (not analysed for scrap).
    exhaust_smoke = models.CharField(max_length=10, choices=ExhaustSmoke.choices, blank=True, default="")
    # Final-section 5-star ratings (1–5). Auction shows all six; scrap → exterior only.
    rating_exterior   = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_interior   = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_engine     = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_suspension = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_ac         = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_brake      = models.PositiveSmallIntegerField(null=True, blank=True)
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
    file         = models.FileField(upload_to="inspections/media/raw/", max_length=255, blank=True, null=True)
    webp_file    = models.ImageField(upload_to="inspections/media/webp/", max_length=255, blank=True, null=True)
    mp4_file     = models.FileField(upload_to="inspections/media/mp4/", max_length=255, blank=True, null=True)
    masked_file  = models.ImageField(upload_to="inspections/media/masked/", max_length=255, blank=True, null=True)
    plate_masked = models.BooleanField(default=False)
    needs_transcode = models.BooleanField(default=False)
    transcoded      = models.BooleanField(default=False)
    gps_lat      = models.FloatField(null=True, blank=True)
    gps_lng      = models.FloatField(null=True, blank=True)
    captured_at  = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    @property
    def image(self):
        return self.webp_file or self.masked_file or (self.file if self.kind == self.Kind.PHOTO else None)

    def __str__(self): return f"{self.get_kind_display()} · {self.slot or self.section}"


class VehicleRegistryData(models.Model):
    """Cached RC/VAHAN registry pull for a vehicle (§6/§7). Captured once at
    listing (Surepass) and reused at inspection so the inspector VERIFIES rather
    than retypes — never re-billed for the same vehicle. Thin by design: the
    parsed fields already live on Vehicle; this stores the raw payload + source
    + fetched_at for audit, caching, and the 'fetched <date>' prefill label."""
    class Source(models.TextChoices):
        SUREPASS = "surepass", "Surepass / VAHAN"
        OCR      = "ocr",      "RC OCR"
        MANUAL   = "manual",   "Manual entry"

    vehicle    = models.OneToOneField(Vehicle, on_delete=models.CASCADE, related_name="registry")
    reg_number = models.CharField(max_length=20, blank=True)
    raw_json   = models.JSONField(default=dict, blank=True)
    owner_name = models.CharField(max_length=200, blank=True)
    source     = models.CharField(max_length=10, choices=Source.choices, default=Source.SUREPASS)
    fetched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self): return f"Registry · {self.reg_number or self.vehicle} · {self.source}"


class CheckpointPhoto(models.Model):
    """Multiple condition photos per checkpoint. Checkpoints are stored as JSON
    on InspectionReport (Pattern B), so a checkpoint is identified by section +
    checkpoint_key (the part key, e.g. section='exterior', key='bonnet')."""
    report         = models.ForeignKey(InspectionReport, on_delete=models.CASCADE, related_name="checkpoint_photos")
    section        = models.CharField(max_length=40)
    checkpoint_key = models.CharField(max_length=120)
    image          = models.ImageField(upload_to="inspections/media/checkpoints/webp/", max_length=255)
    uploaded_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at"]

    def __str__(self): return f"CheckpointPhoto({self.section}/{self.checkpoint_key})"
