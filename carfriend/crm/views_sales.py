from django.shortcuts import render, redirect, get_object_or_404

from accounts.decorators import sales_required
from accounts.models import DealerProfile
from auctions.models import OCBListing
from core.models import log
from deals.models import Deal
from notifications.services import notify


@sales_required
def dealers(request):
    return render(request, "teams/dealers.html", {"active": "dealers", "dealers": DealerProfile.objects.all()})


@sales_required
def dealer_detail(request, id):
    d = get_object_or_404(DealerProfile, id=id)
    return render(request, "teams/dealer.html", {
        "active": "dealers",
        "d":    d,
        "comms": d.user.dealer_comms.all(),
        "ocb":  d.user.ocb_offers.all(),
    })


@sales_required
def deal_pipeline(request):
    return render(
        request, "teams/deals.html",
        {"active": "deals", "deals": Deal.objects.filter(assigned_sales=request.user)},
    )


@sales_required
def ocb_assign(request):
    if request.method == "POST":
        ocb = get_object_or_404(OCBListing, id=request.POST["ocb_id"])
        ocb.assigned_to_id = request.POST["dealer_id"]
        ocb.save()
        log(request.user, "ocb.assign", ocb, request, dealer=ocb.assigned_to_id)
        if ocb.assigned_to:
            notify(
                ocb.assigned_to, "bid_update",
                title=f"OCB offer: {ocb.vehicle.title}",
                body=f"One Click Buy at ₹{ocb.ocb_price:,}.",
            )
        return redirect("/ocb")
    return render(
        request, "teams/ocb.html",
        {"active": "ocb", "listings": OCBListing.objects.filter(status="open")},
    )
