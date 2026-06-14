from django.contrib import admin

from .models import HomepageLead


@admin.register(HomepageLead)
class HomepageLeadAdmin(admin.ModelAdmin):
    list_display = ("phone", "make", "model", "year", "fuel_type",
                    "plate_number", "est_price_low", "est_price_high",
                    "source", "is_contacted", "created_at")
    list_filter = ("source", "is_contacted", "fuel_type", "created_at")
    search_fields = ("phone", "plate_number", "make", "model")
    readonly_fields = ("created_at",)
    list_editable = ("is_contacted",)
