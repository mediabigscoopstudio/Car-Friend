from django.contrib import admin
from .models import FeatureToggle, AuditLog


@admin.register(FeatureToggle)
class FeatureToggleAdmin(admin.ModelAdmin):
    list_display  = ("label", "key", "enabled", "updated_at")
    list_editable = ("enabled",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display    = ("created_at", "actor", "action", "target_type", "target_id")
    list_filter     = ("action", "target_type")
    search_fields   = ("action", "target_id")
    readonly_fields = [f.name for f in AuditLog._meta.fields]
