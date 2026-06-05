from django.contrib import admin
from .models import KYCVerification


@admin.register(KYCVerification)
class KYCAdmin(admin.ModelAdmin):
    list_display  = ("subject", "kind", "status", "reviewed_by", "created_at")
    list_filter   = ("kind", "status")
    search_fields = ("subject__username", "provider_ref")
