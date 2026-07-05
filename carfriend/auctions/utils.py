from django.utils import timezone

from auctions.models import Auction


def auto_close_expired_auctions():
    """Close live auctions whose end_at has passed AND transition each car's lead to
    'auction_closed' — the seller-decision stage. Without the lead transition the
    seller journey would stick at "In auction" (or square-one) after a car's auction
    ends; this is what actually writes the post-auction decision state.

    Only the just-expired live auctions do per-lead work (usually zero), so it stays
    cheap to call on every dashboard load. transition_lead is forward-only +
    idempotent, so re-calls are no-ops. Returns the number of auctions closed.
    """
    now = timezone.now()
    expired = list(Auction.objects
                   .filter(status=Auction.Status.LIVE, end_at__lte=now)
                   .select_related("vehicle"))
    if not expired:
        return 0
    Auction.objects.filter(id__in=[a.id for a in expired]).update(
        status=Auction.Status.CLOSED, updated_at=now)
    from crm.services import transition_lead_for_vehicle
    for a in expired:
        transition_lead_for_vehicle(a.vehicle, "auction_closed")
    return len(expired)


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
