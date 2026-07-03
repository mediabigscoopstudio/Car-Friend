"""Retail Head (teams host) — oversight of the whole retail pool.

The Retail Head sees ALL retail associates (assumption A), allocates admin-
approved leads to them, and tracks every lead's live (auto) status. The head is
READ-ONLY on sellers and auctions (assumption C); the only write actions are
allocation / re-allocation (assumption D), every one of which is logged.
"""

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Role, User
from auctions.models import Auction
from crm.models import Lead, LeadAllocation
from crm.services import transition_lead
from notifications.services import notify


def _require_retail_head(request):
    if not request.user.is_authenticated:
        return redirect("/auth/login/")
    if request.user.role != User.ROLE_RETAIL_HEAD and not request.user.is_superuser:
        from accounts.views import get_dashboard_url
        return redirect(get_dashboard_url(request.user))
    return None


def _car(vehicle):
    if not vehicle:
        return "—"
    return f"{vehicle.make} {vehicle.model} {vehicle.year}".strip()


def _safe_next(request, default):
    """Return a POSTed 'next' path only if it is a safe local path, else default.
    Lets the shared /pipeline/<id>/ page send the RH back to itself after a POST."""
    nxt = (request.POST.get("next") or "").strip()
    if nxt.startswith("/") and not nxt.startswith("//"):
        return nxt
    return default


def _retail_associates():
    return User.objects.filter(role=Role.RETAIL, is_suspended=False).order_by("first_name", "username")


def _allocate(lead, associate, head):
    """Set the allocation fields, write the audit row, and auto-advance the
    lead to Assigned via the single transition entrypoint. Returns nothing."""
    previous = lead.assigned_associate
    if previous and previous.id == associate.id:
        return False
    LeadAllocation.objects.create(lead=lead, from_associate=previous,
                                  to_associate=associate, by=head)
    lead.assigned_associate = associate
    lead.allocated_at = timezone.now()
    lead.allocated_by = head
    lead.save(update_fields=["assigned_associate", "allocated_at", "allocated_by", "updated_at"])
    transition_lead(lead, "allocated", actor=head)
    notify(associate, "task_assigned", title="New lead allocated to you",
           body=f"{_car(lead.vehicle)} — admin-approved, ready to work.",
           url="/crm/retail/pipeline/")
    return True


# ── Approved leads (inbox / default landing) ──────────────────────────────────

def rh_approved_leads(request):
    guard = _require_retail_head(request)
    if guard:
        return guard
    leads = (Lead.objects.filter(stage=Lead.STAGE_APPROVED, assigned_associate__isnull=True)
             .select_related("vehicle", "seller").order_by("-updated_at"))
    rows = [{
        "id": l.id,
        "car": _car(l.vehicle),
        "plate": l.vehicle.plate_number if l.vehicle else "",
        "seller": (l.seller.get_full_name() or l.seller.username) if l.seller else "—",
        "price": l.vehicle.expected_price if l.vehicle else None,
    } for l in leads]
    return render(request, "teams/retail_head/approved_leads.html", {
        "rows": rows, "associates": _retail_associates(), "count": len(rows),
    })


@require_POST
def rh_allocate(request):
    guard = _require_retail_head(request)
    if guard:
        return guard
    associate = User.objects.filter(id=request.POST.get("associate_id"), role=Role.RETAIL).first()
    lead_ids = request.POST.getlist("lead_ids")
    if not associate or not lead_ids:
        messages.error(request, "Pick at least one lead and a retail associate.")
        return redirect("/crm/retail-head/")
    leads = Lead.objects.filter(id__in=lead_ids, stage=Lead.STAGE_APPROVED,
                                assigned_associate__isnull=True)
    n = sum(1 for l in leads if _allocate(l, associate, request.user))
    messages.success(request, f"Allocated {n} lead(s) to {associate.get_full_name() or associate.username}.")
    return redirect("/crm/retail-head/")


# ── Retail associates ─────────────────────────────────────────────────────────

def rh_associates(request):
    guard = _require_retail_head(request)
    if guard:
        return guard
    associates = _retail_associates().annotate(
        active_leads=Count("allocated_leads", filter=~Q(allocated_leads__stage=Lead.STAGE_CLOSED)),
        closed_leads=Count("allocated_leads", filter=Q(allocated_leads__stage=Lead.STAGE_CLOSED)),
    )
    return render(request, "teams/retail_head/associates.html", {"associates": associates})


# ── Sellers (read-only) ───────────────────────────────────────────────────────

def rh_sellers(request):
    guard = _require_retail_head(request)
    if guard:
        return guard
    q = (request.GET.get("q") or "").strip()
    sellers = User.objects.filter(role=Role.SELLER).prefetch_related("vehicles")
    if q:
        sellers = sellers.filter(Q(first_name__icontains=q) | Q(username__icontains=q)
                                 | Q(email__icontains=q) | Q(city__icontains=q))
    rows = []
    for s in sellers.order_by("-date_joined")[:300]:
        v = s.vehicles.first()
        rows.append({
            "name": s.get_full_name() or s.username,
            "car": _car(v), "city": s.city or (v.city if v else ""),
            "verified": s.is_kyc_done,
        })
    return render(request, "teams/retail_head/sellers.html", {"rows": rows, "q": q})


# ── Auctions (read-only) ──────────────────────────────────────────────────────

def rh_auctions(request):
    guard = _require_retail_head(request)
    if guard:
        return guard
    status = (request.GET.get("status") or "").strip()
    auctions = Auction.objects.select_related("vehicle", "created_by").order_by("-created_at")
    if status:
        auctions = auctions.filter(status=status)
    rows = []
    for a in auctions[:300]:
        hb = a.highest_bid
        rows.append({
            "id": a.id, "car": _car(a.vehicle), "status": a.get_status_display(),
            "bid": hb.amount if hb else None, "reserve": a.reserve_price,
            "associate": (a.created_by.get_full_name() or a.created_by.username) if a.created_by else "—",
            "ends": a.end_at,
        })
    return render(request, "teams/retail_head/auctions.html", {
        "rows": rows, "status": status, "statuses": Auction.Status.choices,
    })


# ── Lead tracking ─────────────────────────────────────────────────────────────

def rh_lead_tracking(request):
    guard = _require_retail_head(request)
    if guard:
        return guard
    assoc_filter = (request.GET.get("associate") or "").strip()
    stage_filter = (request.GET.get("stage") or "").strip()

    leads = (Lead.objects.filter(assigned_associate__isnull=False)
             .select_related("vehicle", "seller", "assigned_associate").order_by("-updated_at"))
    if assoc_filter:
        leads = leads.filter(assigned_associate_id=assoc_filter)
    if stage_filter:
        leads = leads.filter(stage=stage_filter)

    groups = {}
    for l in leads:
        groups.setdefault(l.assigned_associate_id, {"associate": l.assigned_associate, "leads": []})
        groups[l.assigned_associate_id]["leads"].append(l)

    return render(request, "teams/retail_head/lead_tracking.html", {
        "groups": list(groups.values()),
        "associates": _retail_associates(),
        "stages": Lead.STAGE_CHOICES,
        "assoc_filter": assoc_filter, "stage_filter": stage_filter,
    })


@require_POST
def rh_reallocate(request):
    guard = _require_retail_head(request)
    if guard:
        return guard
    lead = get_object_or_404(Lead, id=request.POST.get("lead_id"))
    associate = User.objects.filter(id=request.POST.get("associate_id"), role=Role.RETAIL).first()
    if not associate:
        messages.error(request, "Pick a valid retail associate.")
        return redirect("/crm/retail-head/lead-tracking/")
    if _allocate(lead, associate, request.user):
        messages.success(request, f"Re-allocated to {associate.get_full_name() or associate.username}.")
    else:
        messages.error(request, "That lead is already assigned to this associate.")
    return redirect("/crm/retail-head/lead-tracking/")


# ── Lead detail + start auction (the SOLE auction-start path) ──────────────────

def rh_lead_detail(request, lead_id):
    """Full view of one approved lead: car + seller details, the inspection report
    (reusing the report PDF viewer), and the Start-auction form. The only surface
    from which an auction can be started."""
    guard = _require_retail_head(request)
    if guard:
        return guard
    from inspections.models import InspectionReport
    from auctions.services import DURATION_PRESETS

    lead = get_object_or_404(Lead.objects.select_related("vehicle", "seller"), id=lead_id)
    vehicle = lead.vehicle
    report = report_url = auction = suggested = None
    if vehicle:
        report = (InspectionReport.objects.filter(visit__vehicle=vehicle)
                  .select_related("visit").order_by("-id").first())
        if report and report.pdf:            # generated at inspection submit
            report_url = report.pdf.url
        auction = (Auction.objects.filter(vehicle=vehicle)
                   .exclude(status=Auction.Status.CLOSED).order_by("-created_at").first())
        suggested = (int(vehicle.expected_price or 0)
                     or (report.est_market_value if report else 0) or None)
    return render(request, "teams/retail_head/lead_detail.html", {
        "lead": lead, "vehicle": vehicle, "seller": lead.seller,
        "report": report, "report_url": report_url, "auction": auction,
        "durations": DURATION_PRESETS, "suggested": suggested,
    })


@require_POST
def rh_start_auction(request, lead_id):
    guard = _require_retail_head(request)
    if guard:
        return guard
    from auctions.services import start_auction

    lead = get_object_or_404(Lead.objects.select_related("vehicle"), id=lead_id)
    dest = _safe_next(request, f"/crm/retail-head/lead/{lead_id}/")
    if not lead.vehicle:
        messages.error(request, "This lead has no car to auction.")
        return redirect(dest)
    raw = (request.POST.get("base_price") or "").replace(",", "").replace("₹", "").strip()
    try:
        base_price = int(float(raw))
    except (TypeError, ValueError):
        base_price = 0
    try:
        start_auction(lead.vehicle, base_price, request.POST.get("duration_minutes"),
                      started_by=request.user)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect(dest)
    messages.success(request, f"Auction started for {_car(lead.vehicle)}.")
    return redirect(dest)


@require_POST
def rh_assign(request, lead_id):
    """Assign ONE lead to a retail associate from a lead page. Reuses _allocate
    (LeadAllocation audit row + notify + transition_lead to 'assigned') — the exact
    same path as the bulk rh_allocate inbox action, not a duplicate."""
    guard = _require_retail_head(request)
    if guard:
        return guard
    lead = get_object_or_404(Lead, id=lead_id)
    dest = _safe_next(request, f"/crm/retail-head/lead/{lead_id}/")
    associate = User.objects.filter(id=request.POST.get("associate_id"), role=Role.RETAIL).first()
    if not associate:
        messages.error(request, "Pick a valid retail associate.")
    elif _allocate(lead, associate, request.user):
        messages.success(request, f"Assigned to {associate.get_full_name() or associate.username}.")
    else:
        messages.error(request, "That lead is already assigned to this associate.")
    return redirect(dest)
