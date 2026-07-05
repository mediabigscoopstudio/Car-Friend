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


def create_ocb_from_counter(auction, base_price, *, actor=None):
    """Seller COUNTERED the highest bid -> create an OCB seeded with that counter.

    ocb_price is stored GROSS (base + margin + GST via core.margin — same grossing
    as auctions); the seller's BASE ask lives on the SellerDecision. Offered to the
    auction WINNER first (tier 1) via offer_to_winner. Idempotent — one active OCB
    per vehicle. assigned_to = the lead's assigned Retail Associate (only they may
    later manage / declare / close it)."""
    from core.margin import gross_breakdown
    from crm.models import Lead

    vehicle = auction.vehicle
    existing = (OCBListing.objects.filter(vehicle=vehicle)
                .exclude(status__in=[OCBListing.Status.AGREEMENT, OCBListing.Status.REJECTED])
                .order_by("-id").first())
    if existing:
        return existing
    lead = Lead.objects.filter(vehicle=vehicle).select_related("assigned_associate").first()
    ocb = OCBListing.objects.create(
        vehicle=vehicle, auction=auction,
        ocb_price=gross_breakdown(int(base_price or 0))["gross"],   # dealer-facing GROSS
        assigned_to=(lead.assigned_associate if lead else None),    # the lead's RA owns it
        status=OCBListing.Status.OPEN,
    )
    offer_to_winner(ocb, actor=actor)
    return ocb


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
        for head in User.objects.filter(role=Role.SALES_HEAD, is_suspended=False):
            notify(head, "task_assigned", title="OCB needs a sales associate",
                   body=f"Winner declined {ocb.vehicle} — assign it from the OCB inbox.",
                   url="/crm/sales-head/")
    return ocb


def mask_label(index):
    """Anonymised dealer label for retail/seller surfaces: Dealer A, B, C…"""
    return f"Dealer {chr(65 + index)}" if index < 26 else f"Dealer #{index + 1}"


def offer_rows(ocb, *, reveal_dealer):
    """Display rows for an OCB's offers. When `reveal_dealer` is False the dealer
    identity is replaced by an anonymised label — enforced here, in the view
    layer, so it can't leak through a template."""
    rows = []
    for i, of in enumerate(ocb.offers.select_related("dealer", "submitted_by").all()):
        if reveal_dealer:
            dealer_label = (of.dealer.get_full_name() or of.dealer.username) if of.dealer else "—"
        else:
            dealer_label = mask_label(i)
        rows.append({
            "id": of.id,
            "price": of.price,
            "notes": of.notes,
            "is_selected": of.is_selected,
            "dealer_label": dealer_label,
            "submitted_by_name": (of.submitted_by.get_full_name() or of.submitted_by.username)
                                 if of.submitted_by else "—",
            "created_at": of.created_at,
        })
    return rows
