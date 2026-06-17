"""Role-scoped landing dashboards (teams host), one view + template per role.

Each dashboard checks the exact role and redirects a wrong-role user to THEIR
own dashboard. No shared if/else template — each role renders its own child of
teams/dash_base.html.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import Avg
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import DealerProfile, Role, User
from auctions.models import OCBListing, OCBOffer
from crm.models import Lead, Task
from deals.models import Deal, HandoverChecklist
from inspections.models import InspectionReport, InspectionVisit


def role_dashboard(expected_role):
    """Allow only `expected_role` (or admin/superuser); else send the user to
    their own dashboard."""
    def deco(view):
        @wraps(view)
        @login_required(login_url="/auth/login/")
        def wrapper(request, *args, **kwargs):
            u = request.user
            if u.role != expected_role and u.role != Role.ADMIN and not u.is_superuser:
                from accounts.views import get_dashboard_url
                return redirect(get_dashboard_url(u))
            return view(request, *args, **kwargs)
        return wrapper
    return deco


# ── Retail Associate ─────────────────────────────────────────────────────────

@role_dashboard(Role.RETAIL)
def retail_dashboard(request):
    mine = Lead.objects.filter(assigned_to=request.user)
    stats = {
        "active":   mine.exclude(stage__in=[Lead.STAGE_CLOSED, Lead.STAGE_UNQUALIFIED]).count(),
        "awaiting": mine.filter(stage__in=[Lead.STAGE_NEGOTIATION, Lead.STAGE_AUCTION]).count(),
        "ocbs":     OCBListing.objects.filter(assigned_to=request.user, status=OCBListing.Status.OPEN).count(),
        "closed":   mine.filter(stage=Lead.STAGE_CLOSED).count(),
    }
    recent = mine.select_related("vehicle", "seller").order_by("-updated_at")[:8]
    return render(request, "teams/dash_retail.html", {"stats": stats, "recent": recent})


# ── Sales Associate ──────────────────────────────────────────────────────────

@role_dashboard(Role.SALES)
def sales_dashboard(request):
    u = request.user
    # Everything is scoped to this Sales Associate — no leads, no seller pipeline.
    active = (OCBListing.objects.filter(sales_associate=u)
              .exclude(status__in=[OCBListing.Status.ACCEPTED, OCBListing.Status.REJECTED]))
    stats = {
        "active_ocbs": active.count(),
        "my_offers":   OCBOffer.objects.filter(submitted_by=u).count(),
        "open_tasks":  Task.objects.filter(assigned_to=u)
                           .exclude(status__in=[Task.Status.DONE, Task.Status.CANCELLED]).count(),
        "deals_won":   Deal.objects.filter(assigned_sales=u).count(),
    }
    rows = (OCBListing.objects.filter(sales_associate=u)
            .select_related("vehicle").prefetch_related("offers").order_by("-created_at")[:8])
    listings = [{
        "ocb": o,
        "my_offers": o.offers.filter(submitted_by=u).count(),
    } for o in rows]
    return render(request, "teams/dash_sales.html", {"stats": stats, "listings": listings})


# ── Lead Manager ─────────────────────────────────────────────────────────────

@role_dashboard(Role.LEAD_MANAGER)
def lead_manager_dashboard(request):
    today = timezone.localdate()
    stats = {
        "total":     Lead.objects.count(),
        "new":       Lead.objects.filter(stage=Lead.STAGE_NEW).count(),
        "qualified": Lead.objects.filter(stage=Lead.STAGE_QUALIFIED, updated_at__date=today).count(),
        "scheduled": Lead.objects.filter(stage=Lead.STAGE_INSP_SCHED).count(),
    }
    recent = (Lead.objects.filter(stage=Lead.STAGE_NEW)
              .select_related("vehicle", "seller").order_by("-created_at")[:8])
    return render(request, "teams/dash_lead_manager.html", {"stats": stats, "recent": recent})


# ── Procurement Associate ────────────────────────────────────────────────────

@role_dashboard(Role.PROCUREMENT)
def procurement_dashboard(request):
    today, now = timezone.localdate(), timezone.now()
    paid = (Deal.objects.filter(status=Deal.Status.PAID)
            .select_related("vehicle", "seller", "dealer").order_by("-updated_at"))
    queue = []
    for d in paid:
        h = getattr(d, "handover", None)
        if h and h.stock_out_at:
            continue
        pay = d.payments.filter(status="confirmed").order_by("-confirmed_at").first()
        queue.append({"deal": d, "confirmed_at": pay.confirmed_at if pay else None})

    done = HandoverChecklist.objects.filter(stock_out_at__isnull=False)
    deltas = [(h.stock_out_at - h.created_at).days for h in done if h.stock_out_at and h.created_at]
    stats = {
        "pending":        len(queue),
        "completed_today": done.filter(stock_out_at__date=today).count(),
        "completed_month": done.filter(stock_out_at__year=now.year, stock_out_at__month=now.month).count(),
        "avg_days":       (round(sum(deltas) / len(deltas), 1) if deltas else None),
    }
    return render(request, "teams/dash_procurement.html", {"stats": stats, "queue": queue})


# ── Inspection Associate ─────────────────────────────────────────────────────

@role_dashboard(Role.INSPECTOR)
def inspection_dashboard(request):
    today, now = timezone.localdate(), timezone.now()
    mine = InspectionVisit.objects.filter(inspector=request.user)
    avg = (InspectionReport.objects.filter(visit__inspector=request.user, score__gt=0)
           .aggregate(a=Avg("score"))["a"])
    stats = {
        "assigned":        mine.count(),
        "completed_month": InspectionReport.objects.filter(
                               visit__inspector=request.user,
                               submitted_at__year=now.year, submitted_at__month=now.month).count(),
        "pending_reports": mine.filter(status__in=[InspectionVisit.Status.SCHEDULED,
                                                   InspectionVisit.Status.INPROGRESS]).count(),
        "avg_score":       (round(avg) if avg else None),
    }
    todays = (mine.filter(scheduled_at__date=today)
              .select_related("vehicle").order_by("scheduled_at"))
    return render(request, "teams/dash_inspection.html", {"stats": stats, "todays": todays})


@role_dashboard(Role.INSPECTOR)
def inspection_visits(request):
    visits = (InspectionVisit.objects.filter(inspector=request.user)
              .select_related("vehicle").order_by("-scheduled_at"))
    return render(request, "teams/inspection_visits.html", {"visits": visits})
