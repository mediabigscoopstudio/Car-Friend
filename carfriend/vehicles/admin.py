from django.contrib import admin
from vehicles.models import Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display   = ('plate_number', 'display_name', 'year', 'seller', 'status',
                      'inspection_report_ready', 'auction_active', 'created_at')
    list_filter    = ('status', 'fuel_type', 'inspection_report_ready', 'auction_active')
    search_fields  = ('plate_number', 'make', 'model', 'seller__email', 'owner_name')
    readonly_fields = ('created_at', 'updated_at')
    list_editable  = ('inspection_report_ready', 'auction_active', 'status')
    ordering       = ('-created_at',)
