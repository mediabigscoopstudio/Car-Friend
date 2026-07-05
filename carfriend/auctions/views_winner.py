"""Auction-winner OCB response (public/www host).

When a Retail Associate creates an OCB it is offered to the auction winner
first. The winner accepts or declines here; on decline it routes to the Sales
Head inbox (assumption B). Only the dealer the OCB was offered to may act.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from auctions.models import OCBListing
from auctions.ocb_services import winner_respond


@login_required(login_url="/auth/login/")
def winner_ocb_list(request):
    offers = (OCBListing.objects.filter(offered_to=request.user,
                                        status=OCBListing.Status.OFFERED_TO_WINNER)
              .select_related("vehicle").order_by("-updated_at"))
    return render(request, "auctions/winner_offers.html", {"offers": offers})


@login_required(login_url="/auth/login/")
def winner_ocb_detail(request, listing_id):
    """Read + act on one OCB offered to this dealer. Uses the dealer-safe
    serialization from views_dealer (no seller PII). Actions post to
    winner_respond_view (accept / pass) — the same endpoint the list uses."""
    from auctions.views_dealer import dealer_vehicle, dealer_inspection, _vehicle_report
    ocb = get_object_or_404(OCBListing.objects.select_related("vehicle"),
                            id=listing_id, offered_to=request.user)
    report = _vehicle_report(ocb.vehicle)
    return render(request, "auctions/winner_ocb_detail.html", {
        "ocb":        ocb,
        "vehicle":    dealer_vehicle(ocb.vehicle),
        "inspection": dealer_inspection(report),
        "can_act":    ocb.status == OCBListing.Status.OFFERED_TO_WINNER,
    })


@login_required(login_url="/auth/login/")
@require_POST
def winner_respond_view(request, listing_id):
    ocb = get_object_or_404(OCBListing.objects.select_related("vehicle"),
                            id=listing_id, offered_to=request.user)
    if ocb.status != OCBListing.Status.OFFERED_TO_WINNER:
        messages.error(request, "This offer is no longer awaiting your response.")
        return redirect("/auctions/ocb/offers/")
    # PASS = decline. Otherwise the dealer submits a GROSS price (match / raise /
    # lower) which goes to the seller to accept or reject.
    if request.POST.get("decision") == "pass":
        winner_respond(ocb, False, actor=request.user)
        messages.success(request, "Offer passed — thank you.")
        return redirect("/auctions/ocb/offers/")
    raw = (request.POST.get("price") or "").replace(",", "").replace("₹", "").strip()
    try:
        price = int(float(raw))
    except (TypeError, ValueError):
        price = 0
    if price <= 0:
        messages.error(request, "Enter a valid amount.")
        return redirect(f"/auctions/ocb/{ocb.id}/")
    # FLOOR: the dealer's GROSS offer must be at least the gross OCB price shown to
    # them. Matching exactly is valid; only strictly-below is rejected. Read
    # ocb.ocb_price BEFORE winner_offer (which overwrites it with the new offer).
    floor = int(ocb.ocb_price or 0)
    if price < floor:
        messages.error(request, f"Your offer must be at least ₹{floor:,} (the One Click Buy price).")
        return redirect(f"/auctions/ocb/{ocb.id}/")
    from auctions.ocb_services import winner_offer
    winner_offer(ocb, price, actor=request.user)
    messages.success(request, "Your offer has been sent to the seller.")
    return redirect("/auctions/ocb/offers/")


# ── Open round: OCB opened to ALL dealers (winner tier exhausted) ──────────────

@login_required(login_url="/auth/login/")
def open_ocb_list(request):
    """Every OCB that has entered the OPEN round — visible to ALL dealers, including
    the auction winner. Winner-first OCBs (offered_to a specific dealer, awaiting
    their response) do NOT appear here: the gate keeps them private to the winner."""
    from auctions.ocb_services import open_round_listings
    ocbs = open_round_listings().select_related("vehicle").order_by("-updated_at")
    # Dealer surface: gross ask, no seller PII. Show whether THIS dealer already bid.
    mine = set(OCBListing.objects.filter(id__in=[o.id for o in ocbs],
                                         offers__dealer=request.user).values_list("id", flat=True))
    rows = [{"ocb": o, "name": f"{o.vehicle.make} {o.vehicle.model} {o.vehicle.year}".strip()
             if o.vehicle else "—", "mine": o.id in mine} for o in ocbs]
    return render(request, "auctions/open_ocb_list.html", {"rows": rows})


@login_required(login_url="/auth/login/")
def open_ocb_detail(request, listing_id):
    """Dealer view of an open-round OCB, with the offer control. Gated: a dealer may
    only reach it in the open round (dealer_can_offer). Dealer-safe serialization —
    no seller identity; the ask is GROSS (the dealer's terms)."""
    from auctions.views_dealer import dealer_vehicle, dealer_inspection, _vehicle_report
    from auctions.ocb_services import dealer_can_offer
    ocb = get_object_or_404(OCBListing.objects.select_related("vehicle"), id=listing_id)
    if not dealer_can_offer(ocb, request.user):
        messages.error(request, "This One Click Buy isn't open for offers.")
        return redirect("/auctions/ocb/open/")
    report = _vehicle_report(ocb.vehicle)
    my_offer = ocb.offers.filter(dealer=request.user).order_by("-id").first()
    return render(request, "auctions/open_ocb_detail.html", {
        "ocb":        ocb,
        "vehicle":    dealer_vehicle(ocb.vehicle),
        "inspection": dealer_inspection(report),
        "floor":      ocb.ocb_price,          # dealer cannot offer below the ask (gross)
        "my_offer":   my_offer,
        "can_act":    True,
    })


@login_required(login_url="/auth/login/")
@require_POST
def open_ocb_offer(request, listing_id):
    """A dealer submits a GROSS offer in the open round (or passes). Floor = the OCB
    ask (ocb_price); an offer at the floor is a valid 'yes at ask price'."""
    from auctions.ocb_services import dealer_can_offer, add_ocb_offer
    ocb = get_object_or_404(OCBListing.objects.select_related("vehicle"), id=listing_id)
    if not dealer_can_offer(ocb, request.user):
        messages.error(request, "This One Click Buy isn't open for offers.")
        return redirect("/auctions/ocb/open/")
    if request.POST.get("decision") == "pass":
        messages.success(request, "Passed — thank you.")
        return redirect("/auctions/ocb/open/")
    raw = (request.POST.get("price") or "").replace(",", "").replace("₹", "").strip()
    try:
        price = int(float(raw))
    except (TypeError, ValueError):
        price = 0
    if price < int(ocb.ocb_price or 0):
        messages.error(request, f"Your offer can't be below the ask of ₹{int(ocb.ocb_price):,}.")
        return redirect(f"/auctions/ocb/open/{ocb.id}/")
    add_ocb_offer(ocb, dealer=request.user, gross=price, submitted_by=request.user)
    messages.success(request, "Your offer has been submitted.")
    return redirect("/auctions/ocb/open/")
