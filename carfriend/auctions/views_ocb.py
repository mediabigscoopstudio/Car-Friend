"""OCB task board — Retail Associate (owns/creates, selects winner) + Sales
Associate (submits dealer offers). Shared OCB detail page with a Retail<->Sales
message thread. Role-scoped on the teams host.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import retail_required, role_required, sales_required
from accounts.models import Role, User
from auctions.models import OCBListing, OCBMessage, OCBOffer
from auctions.ocb_services import offer_rows, offer_to_winner
from core.models import log
from deals.models import Deal
from notifications.services import notify
from vehicles.models import Vehicle


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


def _can_retail(user):
    return user.is_retail or user.is_admin


def _can_sales(user):
    return user.is_sales or user.is_admin


# ── Retail: My OCBs ──────────────────────────────────────────────────────────

@retail_required
def ocb_board(request):
    tasks = (OCBListing.objects.filter(assigned_to=request.user)
             .select_related("vehicle").prefetch_related("offers").order_by("-created_at"))
    return render(request, "teams/ocb_retail.html", {"tasks": tasks})


@retail_required
@require_POST
def ocb_create(request):
    """Create an OCB task from a lead's vehicle, owned by this Retail Associate."""
    vehicle = get_object_or_404(Vehicle, id=request.POST.get("vehicle_id"))
    price = _int(request.POST.get("ocb_price"))
    if price <= 0:
        messages.error(request, "Enter a valid client-suitable price.")
        return redirect(request.POST.get("next") or "/ocb/")
    listing = OCBListing.objects.create(
        vehicle=vehicle, ocb_price=price, assigned_to=request.user,
        status=OCBListing.Status.OPEN)
    if request.POST.get("notes"):
        OCBMessage.objects.create(ocb_listing=listing, sender=request.user,
                                  message=request.POST["notes"].strip())
    log(request.user, "ocb.create", listing, request)
    # Winner-first: offer the OCB to the auction winner before sales gets it.
    offer_to_winner(listing, actor=request.user)
    messages.success(request, "OCB created and offered to the auction winner.")
    return redirect(f"/ocb/{listing.id}/")


@retail_required
@require_POST
def ocb_select(request, offer_id):
    offer = get_object_or_404(OCBOffer.objects.select_related("ocb_listing__vehicle", "dealer"), id=offer_id)
    listing = offer.ocb_listing
    if listing.status != OCBListing.Status.OPEN:
        messages.error(request, "This OCB task is already closed.")
        return redirect(f"/ocb/{listing.id}/")
    listing.offers.update(is_selected=False)
    offer.is_selected = True
    offer.save(update_fields=["is_selected"])
    listing.status = OCBListing.Status.ACCEPTED
    listing.save(update_fields=["status"])

    v = listing.vehicle
    deal = Deal.objects.create(
        vehicle=v, seller=v.seller, dealer=offer.dealer,
        final_price=offer.price, seller_shown_price=listing.ocb_price,
        assigned_sales=offer.submitted_by, status=Deal.Status.OPEN)
    log(request.user, "ocb.close", listing, request, deal_id=deal.id, offer_id=offer.id)
    if offer.submitted_by:
        notify(offer.submitted_by, "task_assigned", title="Your OCB offer was selected",
               body=f"₹{offer.price:,} for {v} — deal opened.", url="/ocb/sales/")
    messages.success(request, "Winning offer selected — deal opened for finalization.")
    return redirect("/ocb/")


# ── Sales: open OCB board ────────────────────────────────────────────────────

@sales_required
def ocb_sales(request):
    tasks = (OCBListing.objects.filter(status=OCBListing.Status.OPEN)
             .select_related("vehicle").prefetch_related("offers").order_by("-created_at"))
    return render(request, "teams/ocb_sales.html", {"tasks": tasks})


@sales_required
@require_POST
def ocb_submit_offer(request, listing_id):
    listing = get_object_or_404(OCBListing, id=listing_id, status=OCBListing.Status.OPEN)
    dealer = User.objects.filter(id=request.POST.get("dealer_id"), role=Role.DEALER).first()
    price = _int(request.POST.get("price"))
    if not dealer or price <= 0:
        messages.error(request, "Pick a dealer and enter a valid offer price.")
        return redirect(f"/ocb/{listing.id}/")
    OCBOffer.objects.create(
        ocb_listing=listing, dealer=dealer, price=price,
        notes=(request.POST.get("notes") or "").strip(), submitted_by=request.user)
    log(request.user, "ocb.offer", listing, request, dealer_id=dealer.id, price=price)
    if listing.assigned_to:
        notify(listing.assigned_to, "task_assigned", title="New dealer offer",
               body=f"₹{price:,} for {listing.vehicle}", url=f"/ocb/{listing.id}/")
    messages.success(request, "Offer submitted to the OCB board.")
    return redirect(f"/ocb/{listing.id}/")


# ── Shared: OCB detail + message thread (Retail + Sales) ─────────────────────

@role_required("retail", "sales")
def ocb_detail(request, listing_id):
    listing = get_object_or_404(OCBListing.objects.select_related("vehicle", "assigned_to"), id=listing_id)
    # Dealer identity is revealed only to the sales side (assumption F).
    offers = offer_rows(listing, reveal_dealer=_can_sales(request.user))
    thread = listing.messages.select_related("sender").all()
    dealers = (User.objects.filter(role=Role.DEALER, is_suspended=False).order_by("username")
               if _can_sales(request.user) else None)
    return render(request, "teams/ocb_detail.html", {
        "listing": listing, "offers": offers, "thread": thread, "dealers": dealers,
        "is_retail": _can_retail(request.user), "is_sales": _can_sales(request.user),
    })


@role_required("retail", "sales")
@require_POST
def ocb_message(request, listing_id):
    listing = get_object_or_404(OCBListing, id=listing_id)
    text = (request.POST.get("message") or "").strip()
    if text:
        OCBMessage.objects.create(ocb_listing=listing, sender=request.user, message=text)
        target = listing.assigned_to if _can_sales(request.user) else None
        if target and target != request.user:
            notify(target, "task_assigned", title="New OCB message",
                   body=text[:80], url=f"/ocb/{listing.id}/")
    return redirect(f"/ocb/{listing.id}/")
