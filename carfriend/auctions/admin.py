from django.contrib import admin
from .models import Auction, Bid, SellerDecision, OCBListing


class BidInline(admin.TabularInline):
    model = Bid; extra = 0


@admin.register(Auction)
class AuctionAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "status", "reserve_price", "reactivation_count", "start_at", "end_at")
    list_filter  = ("status",)
    inlines      = [BidInline]


admin.site.register(Bid)
admin.site.register(SellerDecision)
admin.site.register(OCBListing)
