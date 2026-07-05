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
    from auctions.ocb_services import winner_offer
    winner_offer(ocb, price, actor=request.user)
    messages.success(request, "Your offer has been sent to the seller.")
    return redirect("/auctions/ocb/offers/")
