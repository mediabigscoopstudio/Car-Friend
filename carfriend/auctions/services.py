"""Auction lifecycle services.

`start_auction()` is the ONE and ONLY path that creates an auction. Admin approval
no longer auto-starts auctions; the Retail Head starts them from the lead-info page
(crm.views_retail_head.rh_start_auction), which is the sole entry point. Keeping
creation in a single guarded function is what prevents an auction from ever existing
without a human-set price — permanently killing the ₹0-reserve bug.
"""
import datetime

from django.utils import timezone

from auctions.models import Auction
from core.margin import gross_breakdown
from notifications.services import notify


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
