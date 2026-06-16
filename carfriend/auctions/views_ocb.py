"""OCB task board — Retail Associate (owns the board) + Sales Associate (submits
dealer offers). Role-scoped on the teams host.

Retail creates/owns an OCB task (car + client-suitable price), Sales submits
dealer offers into it, Retail selects the winning offer to close (creates a Deal).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import retail_required, sales_required
from accounts.models import Role, User
from auctions.models import OCBListing, OCBOffer
from core.models import log
from deals.models import Deal
from notifications.services import notify
from vehicles.models import Vehicle


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


# ── Retail: OCB task board ───────────────────────────────────────────────────

@retail_required
def ocb_board(request):
    tasks = (OCBListing.objects.filter(status=OCBListing.Status.OPEN)
             .select_related("vehicle", "assigned_to").prefetch_related("offers__dealer"))
    sales = User.objects.filter(role=Role.SALES, is_suspended=False).order_by("username")
    open_ids = OCBListing.objects.filter(status=OCBListing.Status.OPEN).values_list("vehicle_id", flat=True)
    vehicles = (Vehicle.objects.exclude(status=Vehicle.STATUS_SOLD)
                .exclude(id__in=list(open_ids)).order_by("-created_at")[:50])
    return render(request, "teams/ocb_retail.html",
                  {"tasks": tasks, "sales": sales, "vehicles": vehicles})


@retail_required
@require_POST
def ocb_create(request):
    vehicle = get_object_or_404(Vehicle, id=request.POST.get("vehicle_id"))
    price = _int(request.POST.get("ocb_price"))
    if price <= 0:
        messages.error(request, "Enter a valid client price.")
        return redirect("/ocb/")
    assigned = User.objects.filter(id=request.POST.get("assigned_to"), role=Role.SALES).first()
    listing = OCBListing.objects.create(
        vehicle=vehicle, ocb_price=price, assigned_to=assigned, status=OCBListing.Status.OPEN)
    log(request.user, "ocb.create", listing, request)
    if assigned:
        notify(assigned, "task_assigned",
               title="OCB task assigned",
               body=f"{vehicle} — collect dealer offers.", url="/ocb/sales/")
    messages.success(request, "OCB task created.")
    return redirect("/ocb/")


@retail_required
@require_POST
def ocb_select(request, offer_id):
    offer = get_object_or_404(OCBOffer.objects.select_related("ocb_listing__vehicle", "dealer"), id=offer_id)
    listing = offer.ocb_listing
    if listing.status != OCBListing.Status.OPEN:
        messages.error(request, "This OCB task is already closed.")
        return redirect("/ocb/")
    listing.offers.update(is_selected=False)
    offer.is_selected = True
    offer.save(update_fields=["is_selected"])
    listing.status = OCBListing.Status.ACCEPTED
    listing.save(update_fields=["status"])

    v = listing.vehicle
    deal = Deal.objects.create(
        vehicle=v, seller=v.seller, dealer=offer.dealer,
        final_price=offer.price, seller_shown_price=listing.ocb_price,
        assigned_sales=listing.assigned_to, status=Deal.Status.OPEN)
    log(request.user, "ocb.close", listing, request, deal_id=deal.id, offer_id=offer.id)
    messages.success(request, "Winning offer selected — deal opened for finalization.")
    return redirect("/ocb/")


# ── Sales: submit dealer offers ──────────────────────────────────────────────

@sales_required
def ocb_sales(request):
    tasks = (OCBListing.objects.filter(status=OCBListing.Status.OPEN)
             .select_related("vehicle").prefetch_related("offers__dealer"))
    dealers = User.objects.filter(role=Role.DEALER, is_suspended=False).order_by("username")
    return render(request, "teams/ocb_sales.html", {"tasks": tasks, "dealers": dealers})


@sales_required
@require_POST
def ocb_submit_offer(request, listing_id):
    listing = get_object_or_404(OCBListing, id=listing_id, status=OCBListing.Status.OPEN)
    dealer = User.objects.filter(id=request.POST.get("dealer_id"), role=Role.DEALER).first()
    price = _int(request.POST.get("price"))
    if not dealer or price <= 0:
        messages.error(request, "Pick a dealer and enter a valid offer price.")
        return redirect("/ocb/sales/")
    OCBOffer.objects.create(
        ocb_listing=listing, dealer=dealer, price=price,
        notes=(request.POST.get("notes") or "").strip(), submitted_by=request.user)
    log(request.user, "ocb.offer", listing, request, dealer_id=dealer.id, price=price)
    for r in User.objects.filter(role=Role.RETAIL, is_suspended=False):
        notify(r, "task_assigned",
               title="New dealer offer",
               body=f"₹{price:,} for {listing.vehicle}", url="/ocb/")
    messages.success(request, "Offer submitted to the OCB board.")
    return redirect("/ocb/sales/")
