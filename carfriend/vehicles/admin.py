from django.contrib import admin
from .models import Vehicle, VehiclePhoto, VehicleDocument


class PhotoInline(admin.TabularInline):
    model = VehiclePhoto; extra = 0


class DocInline(admin.TabularInline):
    model = VehicleDocument; extra = 0


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display  = ("title", "year", "seller", "condition_grade", "expected_price", "status")
    list_filter   = ("status", "condition_grade", "make")
    search_fields = ("make", "model", "reg_number")
    inlines       = [PhotoInline, DocInline]
