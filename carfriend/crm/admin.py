from django.contrib import admin
from crm.models import Lead, Bid, LeadAllocation, LeadStatusEvent


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    # `stage` is intentionally NOT list_editable: it is read-only and may only
    # change via crm.services.transition_lead (the master override view routes
    # admin edits through it too), keeping a single source of truth + audit row.
    list_display  = ('vehicle', 'seller', 'assigned_to', 'assigned_associate', 'stage', 'created_at')
    list_filter   = ('stage',)
    list_editable = ('assigned_to',)
    readonly_fields = ('stage',)
    search_fields = ('vehicle__plate_number', 'seller__email')
    ordering      = ('-created_at',)


@admin.register(LeadStatusEvent)
class LeadStatusEventAdmin(admin.ModelAdmin):
    list_display  = ('lead', 'from_status', 'to_status', 'trigger', 'actor', 'created_at')
    list_filter   = ('trigger', 'to_status')
    search_fields = ('lead__vehicle__plate_number',)
    ordering      = ('-created_at',)


@admin.register(LeadAllocation)
class LeadAllocationAdmin(admin.ModelAdmin):
    list_display  = ('lead', 'from_associate', 'to_associate', 'by', 'at')
    ordering      = ('-at',)


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display  = ('vehicle', 'dealer', 'amount', 'is_winning', 'created_at')
    list_editable = ('is_winning',)
    ordering      = ('-amount',)
