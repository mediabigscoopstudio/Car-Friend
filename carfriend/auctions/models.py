import datetime
from django.conf import settings
from django.db import models
from django.utils import timezone
from vehicles.models import Vehicle

REACTIVATION_CAP = 5
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
    def highest_bid(self):
        # Current round only. A re-activated auction resets start_at, so bids from a
        # prior round (created before this round began) are context — NOT live state.
        # This makes the reserve/floor/min-next reset to the new grossed reserve
        # after a re-auction, without touching the WS consumer (it reads this).
        return (self.bids.filter(is_voided=False, created_at__gte=self.start_at)
                .order_by("-amount").first())

    @property
    def current_floor(self):
        # Single source of truth for "next valid bid" — shared by the manual-bid path
        # (consumers.AuctionConsumer.place_bid) and the auto-bid engine (services.run_auto_bids).
        hb = self.highest_bid
        return (hb.amount if hb else self.reserve_price) + self.min_increment

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


class AutoBid(models.Model):
    """A dealer's standing proxy-bid ceiling for one auction. While active, the auto-bid
    engine (services.run_auto_bids) raises the dealer's standing bid on their behalf,
    one min_increment at a time, whenever they're outbid — but never above max_amount.

    One row per (auction, dealer): editing = update max_amount, cancelling = is_active=False,
    re-enabling = update again. This is the persistence layer for "survives page refresh".
    """

    auction    = models.ForeignKey(Auction, on_delete=models.CASCADE, related_name="auto_bids")
    dealer     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auto_bids")
    max_amount = models.PositiveIntegerField()
    is_active  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["auction", "dealer"], name="uniq_autobid_per_dealer_auction")]

    def __str__(self): return f"Auto-bid ≤₹{self.max_amount:,} by {self.dealer} on {self.auction_id}"


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
        # Full OCB lifecycle (BSS-2026-CF-SPEC v3.1, Part D). Legacy values
        # (OPEN/ACCEPTED/COUNTERED/REJECTED) are kept so old rows stay valid.
        OPEN              = "open",              "Open"
        OFFERED_TO_WINNER = "offered_to_winner", "Offered to auction winner"
        WINNER_ACCEPTED   = "winner_accepted",   "Winner accepted"
        WINNER_DECLINED   = "winner_declined",   "Winner declined"
        ASSIGNED_TO_SALES = "assigned_to_sales", "Assigned to sales associate"
        DEALERS_CONTACTED = "dealers_contacted", "Dealers contacted"
        SELLER_ACCEPTED   = "seller_accepted",   "Seller accepted price"
        AGREEMENT         = "agreement",         "Agreement"
        ACCEPTED          = "accepted",          "Accepted (legacy)"
        COUNTERED         = "countered",         "Countered (legacy)"
        REJECTED          = "rejected",          "Rejected (legacy)"

    vehicle     = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="ocb_listings")
    auction     = models.ForeignKey(Auction, null=True, blank=True, on_delete=models.SET_NULL)
    ocb_price   = models.PositiveIntegerField()
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL, related_name="ocb_offers")
    # The Sales Associate this OCB is assigned to (set by Retail at creation).
    # Distinct from assigned_to, which is the Retail creator/owner of the OCB.
    sales_associate = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                        on_delete=models.SET_NULL, related_name="sales_ocbs")
    # The auction winner the OCB is offered to first (assumption B). On decline
    # the OCB enters the Sales Head inbox.
    offered_to          = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                            on_delete=models.SET_NULL, related_name="ocbs_offered_to_me")
    winner_responded_at = models.DateTimeField(null=True, blank=True)
    # Set by the Sales Head when assigning a declined OCB to a sales associate.
    assigned_sales_associate = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                                 on_delete=models.SET_NULL, related_name="sales_head_ocbs")
    sales_assigned_at = models.DateTimeField(null=True, blank=True)
    sales_assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                          on_delete=models.SET_NULL, related_name="ocbs_assigned_by_me")
    status      = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
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


class OCBMessage(models.Model):
    """Internal note thread on an OCB task (Retail <-> Sales)."""

    ocb_listing = models.ForeignKey(OCBListing, on_delete=models.CASCADE, related_name="messages")
    sender      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                    related_name="ocb_messages")
    message     = models.TextField()
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self): return f"msg by {self.sender} · OCB {self.ocb_listing_id}"
