from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from accounts.decorators import admin_required, role_required
from core.models import log
from core.margin import base_from_gross, inverse_params
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
    # Seller sees BASE: de-gross every dealer bid into the seller's own terms.
    bid_list = [{
        "amount_fmt": f'{base_from_gross(b.amount)["base"]:,}',
        "label":      f"Dealer #{i + 1}",   # masked — identity never exposed
        "created_at": b.created_at,
        "is_highest": i == 0,
    } for i, b in enumerate(bids)]
    hb = bids[0] if bids else None
    payout = base_from_gross(hb.amount)["base"] if hb else None
    p = inverse_params()   # constants so the live WS ticker de-grosses in JS

    return render(request, "www/auctions/seller_watch.html", {
        "auction":           auction,
        "vehicle":           vehicle,
        "bids":              bid_list,
        "highest_bid":       hb,
        "highest_fmt":       f"{payout:,}" if payout is not None else None,
        "reserve_fmt":       f"{int(vehicle.expected_price):,}" if vehicle.expected_price else f'{base_from_gross(auction.reserve_price)["base"]:,}',
        "min_increment_fmt": f"{auction.min_increment:,}",
        "expected_fmt":      f"{int(vehicle.expected_price):,}" if vehicle.expected_price else None,
        "bid_count":         total,
        "cf_k":              repr(p["k"]),          # JS numeric literals — repr()
        "cf_boundary":       repr(p["boundary"]),   # keeps a '.' decimal regardless
        "cf_floor_gst":      repr(p["floor_gst"]),  # of any template number locale
    })


@login_required(login_url="/auth/login/")
@require_POST
def seller_decision(request, auction_id):
    """Seller's post-auction choice. Additive: records a real SellerDecision and
    only ever sets the VALID 'reauction' status. accept/counter leave the auction
    'closed' for the CRM/OCB pipeline to act on — no invalid status writes."""
    from .models import SellerDecision
    from .utils import auto_close_expired_auctions
    auto_close_expired_auctions()

    auction = get_object_or_404(Auction.objects.select_related("vehicle"), id=auction_id)
    if auction.vehicle.seller_id != request.user.id:
        return JsonResponse({"error": "forbidden"}, status=403)
    if auction.status not in ("closed", "reauction"):
        return JsonResponse({"error": "This auction is not awaiting a decision."}, status=400)
    if auction.seller_decisions.exists():
        return JsonResponse({"error": "A decision has already been made."}, status=400)

    action = request.POST.get("action")

    if action == "accept":
        hb = auction.highest_bid
        if not hb:
            return JsonResponse({"error": "There are no bids to accept."}, status=400)
        SellerDecision.objects.create(auction=auction, decision=SellerDecision.Choice.ACCEPT)
        # Seller accepted the winning GROSS bid -> auto-create the Deal (idempotent).
        from deals.services import create_deal_from_win
        create_deal_from_win(auction.vehicle, hb.amount, hb.dealer, auction.vehicle.seller)
        log(request.user, "auction.seller_accept", auction, request)
        return JsonResponse({"status": "accepted"})

    if action == "counter":
        raw = (request.POST.get("counter_price") or "").replace(",", "").replace("₹", "").strip()
        try:
            amount = int(raw)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Enter a valid counter price."}, status=400)
        if amount <= 0:
            return JsonResponse({"error": "Enter a valid counter price."}, status=400)
        SellerDecision.objects.create(auction=auction, decision=SellerDecision.Choice.COUNTER,
                                      counter_price=amount)
        # A Counter is a REQUEST, not an OCB. Record the seller's SUGGESTED base price
        # (on the SellerDecision) and move the lead to Negotiation. The lead's assigned
        # Retail Associate is the SOLE OCB creator (from the lead page) — so an OCB can
        # never be orphaned. No OCBListing is created here.
        from crm.services import transition_lead_for_vehicle
        from crm.models import Lead
        transition_lead_for_vehicle(auction.vehicle, "seller_countered", actor=request.user)
        lead = Lead.objects.filter(vehicle=auction.vehicle).select_related("assigned_associate").first()
        if lead and lead.assigned_associate:
            notify(lead.assigned_associate, "task_assigned", title="Seller suggested a price",
                   body=f"{auction.vehicle} — seller suggests ₹{amount:,}. Review it and create the OCB.",
                   url=f"/pipeline/{lead.id}/")
        log(request.user, "auction.seller_counter", auction, request, counter=amount)
        return JsonResponse({"status": "countered", "counter_price": amount})

    if action == "reauction":
        SellerDecision.objects.create(auction=auction, decision=SellerDecision.Choice.REAUCTION)
        auction.status = Auction.Status.REAUCTION   # flags the Retail Head to restart it
        auction.save(update_fields=["status"])
        # Re-auction is a REQUEST to the Retail Head, who restarts it from /pipeline/.
        from accounts.models import Role, User
        for head in User.objects.filter(role=Role.RETAIL_HEAD, is_suspended=False):
            notify(head, "task_assigned", title="Re-auction requested",
                   body=f"{auction.vehicle} — the seller asked to re-auction.",
                   url="/crm/retail-head/")
        log(request.user, "auction.seller_reauction", auction, request)
        return JsonResponse({"status": "reauction_requested"})

    return JsonResponse({"error": "invalid action"}, status=400)


# ── Seller-facing auction result / decision + OCB (read-only) ─────────────────

@login_required(login_url="/auth/login/")
def seller_auction_result(request, auction_id):
    """Post-auction decision surface for the seller: shows the highest bid and the
    net payout, and offers Accept / Counter / Re-auction — which POST to the
    existing seller_decision endpoint. Read-only once a decision is recorded."""
    from .models import SellerDecision, OCBListing
    from .utils import auto_close_expired_auctions
    auto_close_expired_auctions()

    auction = get_object_or_404(Auction.objects.select_related("vehicle"), id=auction_id)
    vehicle = auction.vehicle
    if vehicle.seller_id != request.user.id:
        return redirect("/auth/seller/dashboard/")

    hb = auction.highest_bid
    decision = auction.seller_decisions.order_by("-id").first()
    ocb = OCBListing.objects.filter(auction=auction).order_by("-id").first()
    awaiting = auction.status in ("closed", "reauction") and decision is None

    payout = base_from_gross(hb.amount)["base"] if hb else None
    return render(request, "www/auctions/seller_result.html", {
        "auction":      auction,
        "vehicle":      vehicle,
        "highest_bid":  hb,
        "highest_fmt":  f"{payout:,}" if payout is not None else None,
        "reserve_fmt":  f"{int(vehicle.expected_price):,}" if vehicle.expected_price else f'{base_from_gross(auction.reserve_price)["base"]:,}',
        "expected_fmt": f"{int(vehicle.expected_price):,}" if vehicle.expected_price else None,
        "bid_count":    auction.bids.filter(is_voided=False).count(),
        "decision":     decision,
        "counter_fmt":  f"{decision.counter_price:,}" if decision and decision.counter_price else None,
        "ocb":          ocb,
        "ocb_status":   ocb.get_status_display() if ocb else None,
        "awaiting":     awaiting,
    })


@login_required(login_url="/auth/login/")
def seller_ocb(request, auction_id):
    """Read-only post-auction One Click Buy status for the seller. The OCB pipeline
    itself is driven internally; the seller sees the price + status and, when the
    agreement is ready, a link to sign it."""
    from .models import OCBListing
    from deals.models import Deal

    auction = get_object_or_404(Auction.objects.select_related("vehicle"), id=auction_id)
    vehicle = auction.vehicle
    if vehicle.seller_id != request.user.id:
        return redirect("/auth/seller/dashboard/")

    ocb = OCBListing.objects.filter(auction=auction).order_by("-id").first()
    deal = Deal.objects.filter(vehicle=vehicle, seller=request.user).order_by("-id").first()
    # OCB price is stored GROSS (dealer-facing) — de-gross to the seller's base.
    ocb_base = base_from_gross(ocb.ocb_price)["base"] if ocb and ocb.ocb_price else None
    return render(request, "www/auctions/seller_ocb.html", {
        "auction":       auction,
        "vehicle":       vehicle,
        "ocb":           ocb,
        "ocb_status":    ocb.get_status_display() if ocb else None,
        "ocb_price_fmt": f"{ocb_base:,}" if ocb_base is not None else None,
        "winner_offer_pending": bool(ocb and ocb.status == OCBListing.Status.WINNER_ACCEPTED),
        # "accepted" = the all-dealers path where the RA selected a winning offer;
        # the template also requires `deal`, so a legacy accepted OCB with no Deal
        # never shows a stray sign link.
        "ocb_signable":  bool(ocb and ocb.status in ("seller_accepted", "agreement", "accepted")),
        "deal":          deal,
    })


@login_required(login_url="/auth/login/")
@require_POST
def seller_ocb_respond(request, auction_id):
    """Seller accepts or rejects the auction WINNER's OCB offer (tier 1). Accept ->
    Deal from the winner's GROSS price (idempotent) + agreement. Reject -> the OCB
    goes to the lead's Retail Associate to DECLARE to the all-dealers tier."""
    from .models import OCBListing
    auction = get_object_or_404(Auction.objects.select_related("vehicle"), id=auction_id)
    if auction.vehicle.seller_id != request.user.id:
        return redirect("/auth/seller/dashboard/")
    ocb = OCBListing.objects.filter(auction=auction).order_by("-id").first()
    if not ocb or ocb.status != OCBListing.Status.WINNER_ACCEPTED:
        return redirect(f"/auctions/{auction_id}/ocb/")
    if request.POST.get("action") == "accept":
        from deals.services import create_deal_from_win
        create_deal_from_win(ocb.vehicle, ocb.ocb_price, ocb.offered_to, ocb.vehicle.seller)
        ocb.status = OCBListing.Status.SELLER_ACCEPTED
        ocb.save(update_fields=["status", "updated_at"])
    else:  # reject -> back to the RA to declare (tier 2)
        ocb.status = OCBListing.Status.WINNER_DECLINED
        ocb.save(update_fields=["status", "updated_at"])
        if ocb.assigned_to:
            notify(ocb.assigned_to, "task_assigned", title="Seller declined the winner's offer",
                   body=f"{ocb.vehicle} — declare it to open the all-dealers tier.", url="/crm/retail/ocb/")
    return redirect(f"/auctions/{auction_id}/ocb/")


@admin_required
def auctions_overview(request):
    """Master READ-ONLY live console: only currently-live auctions, searchable by
    vehicle number. No actions — auctions are controlled by the Retail Head."""
    from auctions.utils import auto_close_expired_auctions
    auto_close_expired_auctions()
    q = (request.GET.get("q") or "").strip()
    qs = (Auction.objects.filter(status=Auction.Status.LIVE)
          .select_related("vehicle").prefetch_related("bids").order_by("-start_at"))
    if q:
        qs = qs.filter(vehicle__plate_number__icontains=q)
    rows = []
    for a in qs:
        hb = a.highest_bid
        rows.append({
            "id": a.id, "vehicle": a.vehicle,
            "bidders": a.bids.filter(is_voided=False).values("dealer").distinct().count(),
            "highest": hb.amount if hb else a.reserve_price,
            "end_at": a.end_at,
        })
    return render(request, "master/auctions.html", {"active": "auctions", "rows": rows, "q": q})


@admin_required
def master_auction_live(request, id):
    """Master READ-ONLY full live view of ONE auction: car + the reused dealer
    inspection viewer, a real-time named bid feed (real dealer names), and BOTH
    money sides (dealer GROSS + seller BASE), live off the SAME WebSocket the
    dealer room uses. No bidding, no action buttons."""
    from auctions.utils import auto_close_expired_auctions
    from auctions.views_dealer import live_room_context
    auto_close_expired_auctions()
    a = get_object_or_404(Auction.objects.select_related("vehicle"), id=id)
    ctx = live_room_context(a, "/auctions_overview")
    ctx["active"] = "auctions"
    return render(request, "master/auction_live.html", ctx)


# Auction actions are Retail-Head-only now. Master is READ-ONLY on auctions: these
# legacy master endpoints are neutered to a no-op redirect — no start / re-auction
# / terminate / bid-void anywhere in master.
@admin_required
def auction_reactivate(request, id):
    return redirect("/auctions_overview")


@admin_required
def auction_pause(request, id):
    return redirect("/auctions_overview")


@admin_required
def bid_void(request, id):
    return redirect("/auctions_overview")


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
