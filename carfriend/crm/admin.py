from django.contrib import admin
from .models import Lead, NegotiationOffer, CommunicationLog, Task


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("seller", "stage", "assigned_to", "expected_price", "created_at")
    list_filter  = ("stage",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "assigned_to", "due_at", "status")
    list_filter  = ("kind", "status")


admin.site.register(NegotiationOffer)
admin.site.register(CommunicationLog)
