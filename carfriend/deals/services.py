"""Deal creation service.

`create_deal_from_win()` is the single place a Deal is created when a seller
ACCEPTS a winning price — from a live auction's highest bid OR a selected OCB
offer. Both accept paths converge here, so the money split lives in exactly one
place.

It splits the winning GROSS price back to the seller's BASE via core.margin
(spec §2 / §2.6): the dealer pays GROSS, the seller is shown/paid BASE, and the
margin + GST is CarFriend's cut (recorded on the Deal). The RC amount
(CF_RC_HOLD) is a SEPARATE payment (Step 5) and is only *recorded* here as an
additional charge — it is NOT folded into grand_total.

Idempotent: one active Deal per vehicle. Does NOT create Payment rows (Step 5)
and does NOT touch the agreement / e-sign (Step 4).
"""
from django.conf import settings

from core.margin import base_from_gross
from deals.models import Deal
from notifications.services import notify


def create_deal_from_win(vehicle, winning_gross, dealer, seller, assigned_sales=None):
    """Create — or return the existing — Deal for `vehicle` from a winning GROSS
    price. Returns the Deal.

    Idempotent: if a non-closed Deal already exists for the vehicle it is returned
    unchanged (never two active Deals for one car). Money fields are derived from
    core.margin.base_from_gross(winning_gross):

        final_price        = winning_gross            # dealer's gross price
        seller_shown_price = base                     # seller's base (payout)
        cf_commission      = margin
        gst_percentage     = settings.CF_GST_PERCENT
        gst_amount         = gst
        grand_total        = winning_gross            # RC is a SEPARATE payment
        additional_charges = [{"label": "RC transfer", "amount": CF_RC_HOLD}]
        status             = 'agreement'              # awaiting agreement / e-sign
    """
    existing = (Deal.objects.filter(vehicle=vehicle)
                .exclude(status=Deal.Status.CLOSED).order_by("-id").first())
    if existing:
        return existing

    winning_gross = int(winning_gross or 0)
    split = base_from_gross(winning_gross)
    deal = Deal.objects.create(
        vehicle=vehicle,
        seller=seller,
        dealer=dealer,
        assigned_sales=assigned_sales,
        final_price=winning_gross,
        seller_shown_price=split["base"],
        cf_commission=split["margin"],
        gst_percentage=settings.CF_GST_PERCENT,
        gst_amount=split["gst"],
        grand_total=winning_gross,
        additional_charges=[{"label": "RC transfer", "amount": int(settings.CF_RC_HOLD)}],
        status=Deal.Status.AGREEMENT,
    )

    # Lead -> seller_approved (deal created, heading to agreement). Forward-only:
    # for an OCB lead already at the same rank this is a harmless no-op.
    from crm.services import transition_lead_for_vehicle
    transition_lead_for_vehicle(vehicle, "seller_approved", actor=seller)

    # Seller sees BASE; dealer sees GROSS (the gross/base invariant).
    if seller:
        notify(seller, "deal_confirmed",
               title=f"Sale confirmed: {vehicle.display_name}",
               body=f"You'll receive ₹{split['base']:,}. Your agreement is being prepared.")
    if dealer:
        notify(dealer, "deal_confirmed",
               title=f"You won: {vehicle.display_name}",
               body=f"Deal for ₹{winning_gross:,}. Your agreement is being prepared.")
    return deal
