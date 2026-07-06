"""Sales Head (teams host) — oversight of the whole sales pool.

The Sales Head sees ALL sales associates (assumption A), assigns declined OCBs
(now actionable leads) to them, allocates dealers, and tracks live dealer
offers. READ-ONLY on dealers except for allocation (assumption C/D). Dealer
identities ARE visible here — this is the sales side (assumption F).
"""

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Role, User
from auctions.models import OCBListing
from crm.models import DealerAllocation
from crm.services import transition_lead_for_vehicle
from notifications.services import notify


def _require_sales_head(request):
    if not request.user.is_authenticated:
        return redirect("/auth/login/")
    if request.user.role != User.ROLE_SALES_HEAD and not request.user.is_superuser:
        from accounts.views import get_dashboard_url
        return redirect(get_dashboard_url(request.user))
    return None


def _car(vehicle):
    if not vehicle:
        return "—"
    return f"{vehicle.make} {vehicle.model} {vehicle.year}".strip()


def _sales_associates():
    return User.objects.filter(role=Role.SALES, is_suspended=False).order_by("first_name", "username")


# ── OCB inbox (default landing) ───────────────────────────────────────────────

def sh_ocb_inbox(request):
    guard = _require_sales_head(request)
    if guard:
        return guard
    # Inbox = OCBs the assigned Retail Associate has DECLARED to the all-dealers
    # tier (status ASSIGNED_TO_SALES) but no Sales Associate is assigned yet.
    ocbs = (OCBListing.objects.filter(status=OCBListing.Status.ASSIGNED_TO_SALES,
                                      assigned_sales_associate__isnull=True)
            .select_related("vehicle").order_by("-updated_at"))
    rows = [{"id": o.id, "car": _car(o.vehicle), "price": o.ocb_price} for o in ocbs]
    return render(request, "teams/sales_head/ocb_inbox.html", {
        "rows": rows, "associates": _sales_associates(), "count": len(rows),
    })


@require_POST
def sh_ocb_assign(request):
    guard = _require_sales_head(request)
    if guard:
        return guard
    ocb = get_object_or_404(OCBListing.objects.select_related("vehicle"), id=request.POST.get("ocb_id"))
    associate = User.objects.filter(id=request.POST.get("associate_id"), role=Role.SALES).first()
    # Optional safe local redirect target (e.g. back to /pipeline/<id>/); default inbox.
    nxt = (request.POST.get("next") or "").strip()
    dest = nxt if (nxt.startswith("/") and not nxt.startswith("//")) else "/crm/sales-head/"
    if not associate:
        messages.error(request, "Pick a valid sales associate.")
        return redirect(dest)
    fields = ["assigned_sales_associate", "sales_assigned_at", "sales_assigned_by", "updated_at"]
    ocb.assigned_sales_associate = associate
    ocb.sales_assigned_at = timezone.now()
    ocb.sales_assigned_by = request.user
    # Only stamp ASSIGNED_TO_SALES from an open-round/pre-sales state — never regress a
    # winner-first (offered/accepted), seller-accepted, or closed OCB back to it.
    if ocb.status in (OCBListing.Status.OPEN, OCBListing.Status.WINNER_DECLINED,
                      OCBListing.Status.ASSIGNED_TO_SALES, OCBListing.Status.DEALERS_CONTACTED):
        ocb.status = OCBListing.Status.ASSIGNED_TO_SALES
        fields.append("status")
    ocb.save(update_fields=fields)
    # Keep the parent lead in sync (OCB In Progress). Forward-only — a no-op if the
    # lead is already at or past OCB.
    transition_lead_for_vehicle(ocb.vehicle, "ocb_requested", actor=request.user)
    notify(associate, "task_assigned", title="New OCB assigned to you",
           body=f"{_car(ocb.vehicle)} — collect dealer offers.",
           url="/crm/sales/ocb/")
    messages.success(request, f"OCB assigned to {associate.get_full_name() or associate.username}.")
    return redirect(dest)


# ── Sales associates ──────────────────────────────────────────────────────────

def sh_associates(request):
    guard = _require_sales_head(request)
    if guard:
        return guard
    associates = _sales_associates().annotate(
        dealers_allocated=Count("assigned_dealers", distinct=True),
        ocbs_in_progress=Count("sales_head_ocbs",
                               filter=~Q(sales_head_ocbs__status=OCBListing.Status.AGREEMENT),
                               distinct=True),
    )
    return render(request, "teams/sales_head/associates.html", {"associates": associates})


# ── Dealers (read-only) ───────────────────────────────────────────────────────

def sh_dealers(request):
    guard = _require_sales_head(request)
    if guard:
        return guard
    q = (request.GET.get("q") or "").strip()
    dealers = (User.objects.filter(role=Role.DEALER)
               .select_related("dealer_profile", "assigned_sales_associate"))
    if q:
        dealers = dealers.filter(Q(first_name__icontains=q) | Q(username__icontains=q)
                                 | Q(email__icontains=q) | Q(city__icontains=q))
    rows = []
    for d in dealers.order_by("-date_joined")[:300]:
        p = getattr(d, "dealer_profile", None)
        assoc = d.assigned_sales_associate
        rows.append({
            "dealership": p.dealership_name if p else (d.get_full_name() or d.username),
            "city": (p.city if p else "") or d.city,
            "brand": p.brand_interest if p else "",
            "budget": f"₹{p.budget_min:,}–₹{p.budget_max:,}" if p and (p.budget_min or p.budget_max) else "—",
            "associate": (assoc.get_full_name() or assoc.username) if assoc else "—",
        })
    return render(request, "teams/sales_head/dealers.html", {"rows": rows, "q": q})


# ── Dealer allocation ─────────────────────────────────────────────────────────

def sh_dealer_allocation(request):
    guard = _require_sales_head(request)
    if guard:
        return guard
    dealers = (User.objects.filter(role=Role.DEALER)
               .select_related("dealer_profile", "assigned_sales_associate").order_by("-date_joined"))
    rows = []
    for d in dealers[:300]:
        p = getattr(d, "dealer_profile", None)
        assoc = d.assigned_sales_associate
        rows.append({
            "id": d.id,
            "dealership": p.dealership_name if p else (d.get_full_name() or d.username),
            "city": (p.city if p else "") or d.city,
            "current": (assoc.get_full_name() or assoc.username) if assoc else None,
        })
    return render(request, "teams/sales_head/dealer_allocation.html", {
        "rows": rows, "associates": _sales_associates(),
    })


@require_POST
def sh_allocate_dealers(request):
    guard = _require_sales_head(request)
    if guard:
        return guard
    associate = User.objects.filter(id=request.POST.get("associate_id"), role=Role.SALES).first()
    dealer_ids = request.POST.getlist("dealer_ids")
    if not associate or not dealer_ids:
        messages.error(request, "Pick at least one dealer and a sales associate.")
        return redirect("/crm/sales-head/dealer-allocation/")
    dealers = User.objects.filter(id__in=dealer_ids, role=Role.DEALER)
    n = 0
    for d in dealers:
        previous = d.assigned_sales_associate
        if previous and previous.id == associate.id:
            continue
        DealerAllocation.objects.create(dealer=d, from_associate=previous,
                                        to_associate=associate, by=request.user)
        d.assigned_sales_associate = associate
        d.dealer_allocated_at = timezone.now()
        d.dealer_allocated_by = request.user
        d.save(update_fields=["assigned_sales_associate", "dealer_allocated_at",
                              "dealer_allocated_by", "updated_at"])
        n += 1
    if n:
        notify(associate, "task_assigned", title="Dealers allocated to you",
               body=f"{n} dealer(s) added to your network.", url="/crm/sales/ocb/")
    messages.success(request, f"Allocated {n} dealer(s) to {associate.get_full_name() or associate.username}.")
    return redirect("/crm/sales-head/dealer-allocation/")


# ── OCB tracking ──────────────────────────────────────────────────────────────

def sh_ocb_tracking(request):
    guard = _require_sales_head(request)
    if guard:
        return guard
    assoc_filter = (request.GET.get("associate") or "").strip()
    ocbs = (OCBListing.objects.filter(assigned_sales_associate__isnull=False)
            .select_related("vehicle", "assigned_sales_associate")
            .prefetch_related("offers__dealer", "offers__submitted_by").order_by("-updated_at"))
    if assoc_filter:
        ocbs = ocbs.filter(assigned_sales_associate_id=assoc_filter)

    groups = {}
    for o in ocbs:
        groups.setdefault(o.assigned_sales_associate_id,
                          {"associate": o.assigned_sales_associate, "ocbs": []})
        # Dealer identity IS shown here — sales side (assumption F).
        offers = [{"dealer": (of.dealer.get_full_name() or of.dealer.username) if of.dealer else "—",
                   "amount": of.price, "at": of.created_at, "selected": of.is_selected}
                  for of in o.offers.all()]
        groups[o.assigned_sales_associate_id]["ocbs"].append({
            "car": _car(o.vehicle), "price": o.ocb_price,
            "status": o.get_status_display(), "offers": offers,
        })

    return render(request, "teams/sales_head/ocb_tracking.html", {
        "groups": list(groups.values()),
        "associates": _sales_associates(), "assoc_filter": assoc_filter,
    })
