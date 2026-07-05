"""OCB lifecycle services (BSS-2026-CF-SPEC v3.1, Part D).

Centralises the winner-first offer flow and the server-side dealer-identity
masking so the rules can't drift between the several OCB surfaces. Dealer
identity must NEVER reach a seller- or retail-facing view (assumption F); only
the sales side may see it.
"""

from django.utils import timezone

from accounts.models import Role, User
from auctions.models import Auction, OCBListing
from notifications.services import notify


def _winner_dealer(ocb):
    """The dealer who should be offered the OCB first: the highest bidder on the
    related auction (explicit link if present, else the vehicle's latest)."""
    auction = ocb.auction or (Auction.objects.filter(vehicle=ocb.vehicle)
                              .order_by("-created_at").first())
    hb = auction.highest_bid if auction else None
    return hb.dealer if hb else None


def offer_to_winner(ocb, *, actor=None):
    """On OCB creation: offer it to the auction winner first (assumption B).

    If there is no auction winner to offer to, the OCB stays OPEN (the legacy
    direct path). Keeps the parent lead in sync (OCB In Progress)."""
    from crm.services import transition_lead_for_vehicle

    winner = _winner_dealer(ocb)
    if winner:
        ocb.offered_to = winner
        ocb.status = OCBListing.Status.OFFERED_TO_WINNER
        ocb.save(update_fields=["offered_to", "status", "updated_at"])
        notify(winner, "task_assigned", title="An offer is waiting for you",
               body=f"You won {ocb.vehicle} — accept the counter-offer or pass.",
               url="/auctions/ocb/offers/")
    transition_lead_for_vehicle(ocb.vehicle, "ocb_requested", actor=actor)
    return ocb


# NOTE: `create_ocb_from_counter` was REMOVED. A seller Counter is now a REQUEST,
# not an OCB — it records the seller's suggested base price and moves the lead to
# Negotiation. The lead's assigned Retail Associate is the SOLE OCB creator
# (crm.views_retail.retail_lead_create_ocb), which stamps assigned_to = that RA so
# an OCB can never be orphaned (the old auto-path set assigned_to null when no RA
# was allocated yet — that produced orphan OCB id=5).


def winner_respond(ocb, accepted, *, actor=None):
    """The auction winner accepts or declines the OCB offered to them.

    Accept → winner_accepted (sales side never actioned; lead → seller approved).
    Decline → winner_declined → lands in the Sales Head OCB inbox."""
    from crm.services import transition_lead_for_vehicle

    ocb.winner_responded_at = timezone.now()
    if accepted:
        ocb.status = OCBListing.Status.WINNER_ACCEPTED
        ocb.save(update_fields=["status", "winner_responded_at", "updated_at"])
        transition_lead_for_vehicle(ocb.vehicle, "seller_approved", actor=actor)
    else:
        ocb.status = OCBListing.Status.WINNER_DECLINED
        ocb.save(update_fields=["status", "winner_responded_at", "updated_at"])
        # Tier 1 exhausted -> the lead's Retail Associate manages it and DECLARES to
        # the all-dealers tier (Phase 3). Notify the RA, not the Sales Head directly.
        if ocb.assigned_to:
            notify(ocb.assigned_to, "task_assigned", title="Winner passed on an OCB",
                   body=f"{ocb.vehicle} — declare it to open the all-dealers tier.",
                   url="/crm/retail/ocb/")
    return ocb


def winner_offer(ocb, gross_price, *, actor=None):
    """Auction winner responds with their own GROSS price (match / raise / lower).
    Sets ocb_price, marks winner_accepted (awaiting the SELLER), and notifies the
    seller (as BASE) and the lead's Retail Associate (base only — NEVER a dealer
    identity)."""
    from core.margin import base_from_gross
    ocb.ocb_price = int(gross_price or 0)
    ocb.winner_responded_at = timezone.now()
    ocb.status = OCBListing.Status.WINNER_ACCEPTED
    ocb.save(update_fields=["ocb_price", "winner_responded_at", "status", "updated_at"])
    base = base_from_gross(ocb.ocb_price)["base"]
    seller = ocb.vehicle.seller
    if seller:
        notify(seller, "task_assigned", title="Buyer responded to your counter",
               body=f"An offer of ₹{base:,} is ready — accept or decline it.",
               url=(f"/auctions/{ocb.auction_id}/ocb/" if ocb.auction_id else "/auth/seller/dashboard/"))
    if ocb.assigned_to:
        notify(ocb.assigned_to, "task_assigned", title="Winner responded on an OCB",
               body=f"{ocb.vehicle} — an offer of ₹{base:,} awaits the seller.", url="/crm/retail/ocb/")
    return ocb


def mask_label(index):
    """Anonymised dealer label for retail/seller surfaces: Dealer A, B, C…"""
    return f"Dealer {chr(65 + index)}" if index < 26 else f"Dealer #{index + 1}"


def offer_rows(ocb, *, reveal_dealer, as_base=False):
    """Display rows for an OCB's offers. When `reveal_dealer` is False the dealer
    identity is replaced by an anonymised label — enforced here, in the view
    layer, so it can't leak through a template. When `as_base` is True the gross
    offer price is de-grossed to the seller-facing BASE — retail/seller surfaces
    must NEVER see gross (the confidentiality wall), so they pass as_base=True."""
    from core.margin import base_from_gross
    rows = []
    for i, of in enumerate(ocb.offers.select_related("dealer", "submitted_by").all()):
        if reveal_dealer:
            dealer_label = (of.dealer.get_full_name() or of.dealer.username) if of.dealer else "—"
        else:
            dealer_label = mask_label(i)
        price = base_from_gross(of.price)["base"] if as_base else of.price
        rows.append({
            "id": of.id,
            "price": price,
            "notes": of.notes,
            "is_selected": of.is_selected,
            "dealer_label": dealer_label,
            "submitted_by_name": (of.submitted_by.get_full_name() or of.submitted_by.username)
                                 if of.submitted_by else "—",
            "created_at": of.created_at,
        })
    return rows
