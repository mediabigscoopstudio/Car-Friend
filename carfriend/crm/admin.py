from django.contrib import admin
from crm.models import Lead, Bid


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display  = ('vehicle', 'seller', 'assigned_to', 'stage', 'created_at')
    list_filter   = ('stage',)
    list_editable = ('stage', 'assigned_to')
    search_fields = ('vehicle__plate_number', 'seller__email')
    ordering      = ('-created_at',)


@admin.register(Bid)
class BidAdmin(admin.ModelAdmin):
    list_display  = ('vehicle', 'dealer', 'amount', 'is_winning', 'created_at')
    list_editable = ('is_winning',)
    ordering      = ('-amount',)
