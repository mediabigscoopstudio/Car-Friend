import datetime
from django.conf import settings
from django.db import models
from django.utils import timezone
from vehicles.models import Vehicle

REACTIVATION_CAP = 10
AUCTION_MINUTES = 30


class Auction(models.Model):
    class Status(models.TextChoices):
        DRAFT     = "draft",     "Draft"
        LIVE      = "live",      "Live"
        CLOSED    = "closed",    "Closed"
        REAUCTION = "reauction", "Re-auction requested"
        COMPLETED = "completed", "Completed"

    vehicle            = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="auctions")
    reserve_price      = models.PositiveIntegerField()
    start_at           = models.DateTimeField()
    end_at             = models.DateTimeField()
    status             = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    reactivation_count = models.PositiveSmallIntegerField(default=0)
    min_increment      = models.PositiveIntegerField(default=5000)
    created_by         = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                           related_name="auctions_created")
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self): return f"Auction · {self.vehicle} · {self.status}"

    @property
    def highest_bid(self): return self.bids.filter(is_voided=False).order_by("-amount").first()

    @property
    def is_live(self):
        return self.status == self.Status.LIVE and self.start_at <= timezone.now() < self.end_at

    def reactivate(self, by_user):
        if self.reactivation_count >= REACTIVATION_CAP:
            raise ValueError(f"Re-activation cap ({REACTIVATION_CAP}) reached for this listing.")
        self.reactivation_count += 1
        self.start_at = timezone.now()
        self.end_at = self.start_at + datetime.timedelta(minutes=AUCTION_MINUTES)
        self.status = self.Status.LIVE
        self.save()
        return self


class Bid(models.Model):
    auction    = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name="bids")
    dealer     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bids")
    amount     = models.PositiveIntegerField()
    is_voided  = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-amount"]

    def __str__(self): return f"₹{self.amount:,} by {self.dealer} on {self.auction_id}"


class SellerDecision(models.Model):
    class Choice(models.TextChoices):
        ACCEPT    = "accept",    "Accept highest bid"
        COUNTER   = "counter",   "Counter the highest bid"
        REAUCTION = "reauction", "Request re-auction"

    auction       = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name="seller_decisions")
    decision      = models.CharField(max_length=10, choices=Choice.choices)
    counter_price = models.PositiveIntegerField(null=True, blank=True)
    note          = models.TextField(blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    def __str__(self): return f"{self.get_decision_display()} · {self.auction_id}"


class OCBListing(models.Model):
    class Status(models.TextChoices):
        OPEN      = "open",      "Open"
        ACCEPTED  = "accepted",  "Accepted"
        COUNTERED = "countered", "Countered"
        REJECTED  = "rejected",  "Rejected"

    vehicle     = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="ocb_listings")
    auction     = models.ForeignKey(Auction, null=True, blank=True, on_delete=models.SET_NULL)
    ocb_price   = models.PositiveIntegerField()
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="ocb_offers")
    status      = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    def __str__(self): return f"OCB ₹{self.ocb_price:,} · {self.vehicle}"


class OCBOffer(models.Model):
    """A dealer offer collected by a Sales Associate against an OCB task.
    The Retail Associate reviews all offers and selects the winner to close."""

    ocb_listing  = models.ForeignKey(OCBListing, on_delete=models.CASCADE, related_name="offers")
    dealer       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                     related_name="ocb_dealer_offers")
    price        = models.PositiveIntegerField()
    notes        = models.TextField(blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="ocb_offers_submitted")
    is_selected  = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-price", "-created_at"]

    def __str__(self): return f"OCB offer ₹{self.price:,} · {self.dealer}"
