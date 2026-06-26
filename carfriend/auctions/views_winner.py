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
@require_POST
def winner_respond_view(request, listing_id):
    ocb = get_object_or_404(OCBListing.objects.select_related("vehicle"),
                            id=listing_id, offered_to=request.user)
    if ocb.status != OCBListing.Status.OFFERED_TO_WINNER:
        messages.error(request, "This offer is no longer awaiting your response.")
        return redirect("/auctions/ocb/offers/")
    accepted = request.POST.get("decision") == "accept"
    winner_respond(ocb, accepted, actor=request.user)
    messages.success(request, "Offer accepted." if accepted else "Offer passed — thank you.")
    return redirect("/auctions/ocb/offers/")
