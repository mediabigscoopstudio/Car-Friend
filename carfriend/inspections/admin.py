from django.contrib import admin
from .models import InspectionVisit, InspectionReport, DentMarker, InspectionMedia


class MediaInline(admin.TabularInline):
    model = InspectionMedia; extra = 0
    readonly_fields = ("plate_masked",)


@admin.register(InspectionVisit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "inspector", "scheduled_at", "status")
    list_filter  = ("status",)


@admin.register(InspectionReport)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("visit", "score", "condition_grade", "is_synced", "submitted_at", "decided_by")
    list_filter  = ("condition_grade", "is_synced")
    inlines      = [MediaInline]


admin.site.register(DentMarker)
