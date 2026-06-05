from django.contrib import admin
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("deal", "amount", "status", "confirmed_by", "confirmed_at")
    list_filter  = ("status",)
