from django.contrib import admin

from .models import Ticket, TicketMessage


class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 0
    readonly_fields = ("author", "created_at")


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "owner", "category", "status", "updated_at")
    list_filter = ("status", "category")
    search_fields = ("subject", "body", "owner__email", "owner__phone")
    inlines = [TicketMessageInline]
