from django.contrib import admin
from .models import InspectionVisit, InspectionReport, DentMarker, InspectionMedia, CheckpointPhoto


class MediaInline(admin.TabularInline):
    model = InspectionMedia; extra = 0
    readonly_fields = ("plate_masked",)


@admin.register(InspectionVisit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "inspector", "scheduled_at", "status")
    list_filter  = ("status",)


@admin.register(InspectionReport)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("visit", "disposition", "score", "condition_grade", "decision", "is_locked", "submitted_at", "decided_by")
    list_filter  = ("disposition", "condition_grade", "decision", "is_locked")
    inlines      = [MediaInline]


@admin.register(InspectionMedia)
class MediaAdmin(admin.ModelAdmin):
    list_display  = ("id", "report", "kind", "slot", "needs_transcode", "transcoded", "created_at")
    list_filter   = ("kind", "needs_transcode", "transcoded")
    search_fields = ("slot", "section")


@admin.register(CheckpointPhoto)
class CheckpointPhotoAdmin(admin.ModelAdmin):
    list_display  = ("id", "report", "section", "checkpoint_key", "uploaded_at")
    list_filter   = ("section",)
    search_fields = ("checkpoint_key",)


admin.site.register(DentMarker)
