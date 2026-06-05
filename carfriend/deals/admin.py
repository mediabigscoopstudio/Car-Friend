from django.contrib import admin
from .models import Deal, DealAgreement


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "seller", "dealer", "final_price", "status")
    list_filter  = ("status",)


admin.site.register(DealAgreement)
