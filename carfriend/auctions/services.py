"""Auction lifecycle services.

`start_auction()` is the ONE and ONLY path that creates an auction. Admin approval
no longer auto-starts auctions; the Retail Head starts them from the lead-info page
(crm.views_retail_head.rh_start_auction), which is the sole entry point. Keeping
creation in a single guarded function is what prevents an auction from ever existing
without a human-set price — permanently killing the ₹0-reserve bug.
"""
import datetime
import logging

from django.utils import timezone

from auctions.models import Auction
from core.margin import gross_breakdown
from notifications.services import notify

logger = logging.getLogger(__name__)


# Duration presets offered to the Retail Head (minutes -> label). Shared by the
# start-auction form and validated here so only a preset can set end_at.
DURATION_PRESETS = [
    (30, "30 minutes"),
    (60, "1 hour"),
    (120, "2 hours"),
    (360, "6 hours"),
    (720, "12 hours"),
    (1440, "24 hours"),
]
DURATION_MINUTES = {m for m, _ in DURATION_PRESETS}
DEFAULT_DURATION = 30


def start_auction(vehicle, base_price, duration_minutes, started_by=None):
    """Create a live auction for `vehicle` — the ONLY auction-creation path.

    - Refuses base_price <= 0 (raises ValueError) so a reserve can never be 0.
    - Persists the seller BASE price (locked once the auction starts) and grosses
      it into the dealer-facing reserve via core.margin.
    - Creates the Auction (live, now .. now+duration; model-default min_increment).
    - Advances the lead (auction_created -> auction_live) and notifies the seller.
    - Idempotent: if a non-closed auction already exists for the vehicle it is
      returned unchanged — never two live auctions for one car.
    """
    base_price = int(base_price or 0)
    if base_price <= 0:
        raise ValueError("Enter a starting price above ₹0 to start the auction.")

    existing = (Auction.objects.filter(vehicle=vehicle)
                .exclude(status=Auction.Status.CLOSED)
                .order_by("-created_at").first())
    if existing:
        return existing

    try:
        duration_minutes = int(duration_minutes)
    except (TypeError, ValueError):
        duration_minutes = DEFAULT_DURATION
    if duration_minutes not in DURATION_MINUTES:
        duration_minutes = DEFAULT_DURATION

    # Price locks at start: persist the base, gross the dealer-facing reserve.
    vehicle.expected_price = base_price
    vehicle.status = vehicle.STATUS_AUCTION
    vehicle.auction_active = True
    vehicle.save(update_fields=["expected_price", "status", "auction_active", "updated_at"])

    now = timezone.now()
    auction = Auction.objects.create(
        vehicle=vehicle,
        reserve_price=gross_breakdown(base_price)["gross"],
        created_by=started_by,
        start_at=now,
        end_at=now + datetime.timedelta(minutes=duration_minutes),
        status=Auction.Status.LIVE,
    )

    from crm.services import transition_lead_for_vehicle
    transition_lead_for_vehicle(vehicle, "auction_created", actor=started_by)
    transition_lead_for_vehicle(vehicle, "auction_live", actor=started_by)

    notify(vehicle.seller, "auction_start",
           title=f"Auction live: {vehicle.display_name}",
           body=f"Your car is in a live auction for {duration_minutes} minutes.")
    return auction


def reauction(auction, base_price, duration_minutes, started_by=None):
    """Re-run an EXISTING (closed / reauction-requested) auction with a fresh base
    price + duration. Reuses the reactivation cap and gross_breakdown — does NOT
    create a second auction. Refuses base<=0 and enforces REACTIVATION_CAP=5
    server-side (raises ValueError). Grossed reserve as always.
    """
    from auctions.models import REACTIVATION_CAP
    if auction.reactivation_count >= REACTIVATION_CAP:
        raise ValueError(f"Re-auction cap ({REACTIVATION_CAP}) reached for this car.")
    base_price = int(base_price or 0)
    if base_price <= 0:
        raise ValueError("Enter a starting price above ₹0 to re-auction.")
    try:
        duration_minutes = int(duration_minutes)
    except (TypeError, ValueError):
        duration_minutes = DEFAULT_DURATION
    if duration_minutes not in DURATION_MINUTES:
        duration_minutes = DEFAULT_DURATION

    vehicle = auction.vehicle
    vehicle.expected_price = base_price
    vehicle.status = vehicle.STATUS_AUCTION
    vehicle.auction_active = True
    vehicle.save(update_fields=["expected_price", "status", "auction_active", "updated_at"])

    now = timezone.now()
    auction.reserve_price = gross_breakdown(base_price)["gross"]
    auction.reactivation_count += 1
    auction.start_at = now
    auction.end_at = now + datetime.timedelta(minutes=duration_minutes)
    auction.status = Auction.Status.LIVE
    auction.save(update_fields=["reserve_price", "reactivation_count", "start_at",
                                "end_at", "status", "updated_at"])

    from crm.services import transition_lead_for_vehicle
    transition_lead_for_vehicle(vehicle, "auction_live", actor=started_by)
    notify(vehicle.seller, "auction_start",
           title=f"Auction relisted: {vehicle.display_name}",
           body=f"Your car is back in a live auction for {duration_minutes} minutes.")
    return auction


def terminate_auction(auction, by_user=None):
    """Force-close a live auction (Retail Head only, enforced by the caller).
    Idempotent — terminating an already-closed auction is a no-op. Advances the
    lead to auction_closed (audited via transition_lead)."""
    if auction.status == Auction.Status.CLOSED:
        return auction
    auction.status = Auction.Status.CLOSED
    auction.save(update_fields=["status", "updated_at"])
    if auction.vehicle.auction_active:
        auction.vehicle.auction_active = False
        auction.vehicle.save(update_fields=["auction_active", "updated_at"])
    from crm.services import transition_lead_for_vehicle
    transition_lead_for_vehicle(auction.vehicle, "auction_closed", actor=by_user)
    return auction


def _extend_anti_snipe(auction):
    """A bid in the last minute extends the clock by 60s. Shared by the manual-bid path
    (consumers.AuctionConsumer.place_bid) and the auto-bid engine below — both create a
    Bid and must apply the same anti-snipe rule."""
    if (auction.end_at - timezone.now()).total_seconds() < 60:
        auction.end_at += datetime.timedelta(seconds=60)
        auction.save(update_fields=["end_at"])


def run_auto_bids(auction):
    """Proxy-bidding engine. MUST be called inside the same transaction.atomic() +
    Auction.objects.select_for_update() block as the triggering bid (a manual bid, or a
    dealer's ceiling being set/raised) — the row lock is what makes this race-safe, not
    the (in-memory, single-process) channel layer.

    After the floor changes, any OTHER dealer with an active AutoBid whose ceiling still
    clears the new floor gets an automatic bid placed on their behalf, at exactly the
    floor — never above it, never above their ceiling. This can cascade (one auto-bid can
    push the floor past another dealer's ceiling), so it loops, one min_increment at a
    time, until no active auto-bid can clear the floor without exceeding its ceiling —
    matching the spec's "incremental bids using the existing minimum increment logic",
    not a single jump to a resolved clearing price.

    Returns the ordered list of broadcast-ready payloads (one per bid placed), shaped like
    AuctionConsumer's existing success payload, for the caller to fan out via broadcast_bids.
    """
    from accounts.models import DealerVerification
    from auctions.models import AutoBid, Bid

    if auction.min_increment <= 0:
        # Defensive: nothing stops min_increment being edited to 0/negative via admin,
        # which would otherwise let two competing auto-bids oscillate forever.
        return []

    payloads = []
    for _ in range(1000):  # safety valve — should always converge (ceiling-bounded, strictly increasing floor)
        hb = auction.highest_bid
        leader_id = hb.dealer_id if hb else None
        floor = auction.current_floor
        candidate = (
            AutoBid.objects
            .filter(auction=auction, is_active=True, max_amount__gte=floor)
            .exclude(dealer_id=leader_id)
            # Re-check verification on every iteration, mirroring the manual-bid path's own
            # per-bid re-check — a dealer whose verification is later revoked must not keep
            # getting auto-bid on their behalf.
            .filter(dealer_id__in=DealerVerification.objects.filter(
                status=DealerVerification.Status.APPROVED).values("dealer_id"))
            .order_by("-max_amount", "created_at")  # highest ceiling wins; earliest breaks ties
            .first()
        )
        if not candidate:
            # TODO(notifications): any active AutoBid here with max_amount < floor just got
            # outbid past its ceiling. Once notification infra is wired up for this event
            # (see notifications.services.notify), fire it to those dealers here.
            # Intentionally not implemented yet — no sending happens.
            break
        bid = Bid.objects.create(auction=auction, dealer_id=candidate.dealer_id, amount=floor)
        _extend_anti_snipe(auction)
        payloads.append({
            "highest": bid.amount,
            "by_id":   bid.dealer_id,
            "ends_at": auction.end_at.isoformat(),
            "count":   auction.bids.count(),
        })
    else:
        logger.warning("run_auto_bids: hit the 1000-iteration safety cap for auction %s — "
                        "cascade may be unresolved.", auction.id)
    return payloads


def broadcast_bids(auction_id, payloads):
    """Fan out auto-placed bid payloads to the live auction WS group from plain
    (synchronous) code — the documented Channels pattern for broadcasting from outside a
    consumer. Mirrors AuctionConsumer.bid_broadcast's payload shape exactly, so connected
    dealers can't tell an auto-placed bid from a manual one."""
    if not payloads:
        return
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    group = f"auction_{auction_id}"
    for payload in payloads:
        async_to_sync(channel_layer.group_send)(group, {"type": "bid.broadcast", "payload": payload})
