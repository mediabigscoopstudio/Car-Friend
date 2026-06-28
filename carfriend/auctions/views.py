from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required

from accounts.decorators import admin_required, role_required
from core.models import log
from notifications.services import notify
from .models import Auction, Bid


# ── Seller-facing live auction watch page (read-only) ─────────────────────────
# A seller watches their own car's auction: masked dealer identities, live bid
# feed over the existing WS, countdown. No bidding, no mutation.

@login_required(login_url="/auth/login/")
def seller_auction_watch(request, auction_id):
    auction = get_object_or_404(Auction.objects.select_related("vehicle"), id=auction_id)
    vehicle = auction.vehicle
    # Only the seller who owns this car may watch it.
    if vehicle.seller_id != request.user.id:
        return redirect("/auth/seller/dashboard/")

    bids = list(auction.bids.filter(is_voided=False).order_by("-amount")[:50])
    total = auction.bids.filter(is_voided=False).count()
    bid_list = [{
        "amount":     b.amount,
        "amount_fmt": f"{b.amount:,}",
        "label":      f"Dealer #{i + 1}",   # masked — identity never exposed
        "created_at": b.created_at,
        "is_highest": i == 0,
    } for i, b in enumerate(bids)]
    hb = bids[0] if bids else None

    return render(request, "www/auctions/seller_watch.html", {
        "auction":           auction,
        "vehicle":           vehicle,
        "bids":              bid_list,
        "highest_bid":       hb,
        "highest_fmt":       f"{hb.amount:,}" if hb else None,
        "reserve_fmt":       f"{auction.reserve_price:,}",
        "min_increment_fmt": f"{auction.min_increment:,}",
        "net_fmt":           f"{int(hb.amount * 0.98):,}" if hb else None,
        "fee_fmt":           f"{int(hb.amount * 0.02):,}" if hb else None,
        "expected_fmt":      f"{int(vehicle.expected_price):,}" if vehicle.expected_price else None,
        "bid_count":         total,
    })


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
        title=f"Re-auction live: {a.vehicle.display_name}",
        body="Your car is back in a live 30-minute auction.",
    )
    return redirect("/auctions_overview")


@admin_required
def auction_pause(request, id):
    a = get_object_or_404(Auction, id=id)
    a.status = "closed"
    a.save()
    # Pipeline: closing the auction advances the lead to Auction Closed.
    from crm.services import transition_lead_for_vehicle
    transition_lead_for_vehicle(a.vehicle, "auction_closed", actor=request.user)
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
        "bids": a.bids.filter(is_voided=False).select_related("dealer").order_by("-created_at")[:50],
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
