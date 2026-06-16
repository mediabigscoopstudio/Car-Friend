"""Role-scoped landing dashboards (teams host), one view + template per role.

Each dashboard checks the exact role and redirects a wrong-role user to THEIR
own dashboard. No shared if/else template — each role renders its own child of
teams/dash_base.html.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import DealerProfile, Role, User
from auctions.models import OCBListing, OCBOffer
from crm.models import Lead
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
    stats = {
        "active_ocbs": OCBListing.objects.filter(status=OCBListing.Status.OPEN).count(),
        "my_offers":   OCBOffer.objects.filter(submitted_by=request.user).count(),
        "dealers":     DealerProfile.objects.count(),
        "closed":      Deal.objects.filter(assigned_sales=request.user, status=Deal.Status.CLOSED).count(),
    }
    rows = list(OCBListing.objects.filter(status=OCBListing.Status.OPEN)
                .select_related("vehicle").order_by("-created_at")[:5])
    if len(rows) < 5:
        rows += list(OCBListing.objects.exclude(status=OCBListing.Status.OPEN)
                     .select_related("vehicle").order_by("-created_at")[:5 - len(rows)])
    listings = [{
        "ocb": o,
        "my_offers": o.offers.filter(submitted_by=request.user).count(),
    } for o in rows]
    return render(request, "teams/dash_sales.html", {"stats": stats, "listings": listings})
