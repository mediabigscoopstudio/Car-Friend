from django.shortcuts import render, redirect, get_object_or_404

from accounts.decorators import admin_required, role_required
from core.models import log
from notifications.services import notify
from .models import Auction, Bid


@admin_required
def auctions_overview(request):
    auctions = Auction.objects.select_related("vehicle").prefetch_related("bids")
    return render(request, "master/auctions.html", {"active": "auctions", "auctions": auctions})


@admin_required
def auction_reactivate(request, id):
    a = get_object_or_404(Auction, id=id)
    try:
        a.reactivate(request.user)
    except ValueError as e:
        return render(request, "master/auctions.html",
                      {"active": "auctions", "auctions": Auction.objects.all(), "error": str(e)})
    log(request.user, "auction.reactivate", a, request, count=a.reactivation_count)
    notify(
        a.vehicle.seller, "auction_start",
        title=f"Re-auction live: {a.vehicle.title}",
        body="Your car is back in a live 30-minute auction.",
    )
    return redirect("/auctions_overview")


@admin_required
def auction_pause(request, id):
    a = get_object_or_404(Auction, id=id)
    a.status = "closed"
    a.save()
    log(request.user, "auction.pause", a, request)
    return redirect("/auctions_overview")


@admin_required
def bid_void(request, id):
    b = get_object_or_404(Bid, id=id)
    b.is_voided = True
    b.save()
    log(request.user, "bid.void", b, request)
    return redirect(f"/auctions_overview")


@role_required("admin", "retail", "sales")
def auction_room(request, id):
    from .models import Auction
    a = get_object_or_404(Auction, id=id)
    return render(request, "auctions/room.html", {
        "active": "auctions",
        "a": a,
        "bids": a.bids.filter(is_voided=False).order_by("-amount")[:50],
        "highest": a.highest_bid,
    })


@admin_required
def lead_hub(request):
    from crm.models import Lead
    from accounts.models import User

    if request.method == "POST":
        lead = get_object_or_404(Lead, id=request.POST["lead_id"])
        lead.assigned_to_id = request.POST["assignee_id"]
        lead.save()
        log(request.user, "lead.assign", lead, request, assignee=lead.assigned_to_id)
        if lead.assigned_to:
            notify(
                lead.assigned_to, "task_assigned",
                title=f"Lead assigned: {lead.seller}",
                body="New seller lead in your pipeline.",
            )
        return redirect("leads")
    return render(
        request, "master/leads.html",
        {
            "active": "pipeline",
            "leads":  Lead.objects.all(),
            "retail": User.objects.filter(role="retail", is_internal=True),
        },
    )
