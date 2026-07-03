from django.utils import timezone

from auctions.models import Auction


def auto_close_expired_auctions():
    """Flip live auctions whose end_at has passed to 'closed' so the seller's
    post-auction decision flow can pick them up.

    Status-only update (matches the manual admin close in views.auction_pause) —
    the OCB / CRM pipeline acts on the closed auction afterwards. Bulk .update()
    so it is cheap to call on every dashboard load and fires no model signals.
    Returns the number of auctions closed.
    """
    return (Auction.objects
            .filter(status=Auction.Status.LIVE, end_at__lte=timezone.now())
            .update(status=Auction.Status.CLOSED, updated_at=timezone.now()))


def reserve_gross(vehicle, report=None):
    """Dealer-facing GROSS reserve for a new auction on `vehicle`
    (base + margin + GST, via core.margin — see the money-model spec §2).

    Base is the seller's ``expected_price``, falling back to the inspection's
    ``est_market_value`` when expected_price is unset. Returns 0 ONLY when the car
    has no valuation at all (both empty) — a genuine data gap surfaced honestly as
    ₹0 rather than a fabricated reserve. The single source of truth for both
    auction-create paths (inspection approval + retail_create_auction).
    """
    from core.margin import gross_breakdown
    base = int(vehicle.expected_price or 0)
    if not base:
        if report is None:
            from inspections.models import InspectionReport
            report = (InspectionReport.objects
                      .filter(visit__vehicle=vehicle)
                      .order_by("-id").first())
        base = int(getattr(report, "est_market_value", 0) or 0) if report else 0
    return gross_breakdown(base)["gross"] if base else 0
