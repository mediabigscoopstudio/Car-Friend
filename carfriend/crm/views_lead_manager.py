"""Lead Manager role dashboard (teams host).

Role-scoped (lead_manager_required) — Lead Managers see only this dashboard and
the lead data; they triage incoming leads, qualify/un-qualify, and book an
inspection by assigning an Inspection Associate.
"""

from datetime import timedelta

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST

from accounts.decorators import lead_manager_required
from accounts.models import Role, User
from core.models import log
from crm.models import Lead
from crm.services import transition_lead
from inspections.models import InspectionVisit
from notifications.services import notify
from vehicles.models import Vehicle

# Consistent per-inspector colour palette (calendar events + legend).
INSPECTOR_PALETTE = ["#2D6CDF", "#0FB5C9", "#FF6A5A", "#5AA9E6",
                     "#7C4DFF", "#E8A33D", "#1B9E77", "#C2185B"]


def _inspector_colour(inspector_id):
    if not inspector_id:
        return "#8595AB"
    return INSPECTOR_PALETTE[inspector_id % len(INSPECTOR_PALETTE)]


_STATUS_PILL = {
    InspectionVisit.Status.SCHEDULED: "Scheduled",
    InspectionVisit.Status.INPROGRESS: "In Progress",
}


def _visit_seller(visit):
    lead = getattr(visit, "lead", None)
    if lead and lead.seller:
        return lead.seller.get_full_name() or lead.seller.username
    if visit.vehicle and visit.vehicle.seller:
        return visit.vehicle.seller.get_full_name() or visit.vehicle.seller.username
    return "—"


@lead_manager_required
def lm_dashboard(request):
    leads = Lead.objects.select_related("vehicle", "seller")
    counts = {
        "new":         leads.filter(stage=Lead.STAGE_NEW).count(),
        "qualified":   leads.filter(stage=Lead.STAGE_QUALIFIED).count(),
        "scheduled":   leads.filter(stage=Lead.STAGE_INSP_SCHED).count(),
        "unqualified": leads.filter(stage=Lead.STAGE_UNQUALIFIED).count(),
    }
    active = leads.exclude(stage__in=[Lead.STAGE_CLOSED, Lead.STAGE_UNQUALIFIED]).order_by("-created_at")
    inspectors = User.objects.filter(role=Role.INSPECTOR, is_suspended=False).order_by("username")
    return render(request, "teams/lead_manager.html", {
        "counts": counts, "leads": active, "inspectors": inspectors,
        "STAGE_NEW": Lead.STAGE_NEW, "STAGE_QUALIFIED": Lead.STAGE_QUALIFIED,
    })


@lead_manager_required
@require_POST
def lm_qualify(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    decision = request.POST.get("decision")
    note = (request.POST.get("note") or "").strip()
    event = {"qualified": "qualified", "unqualified": "unqualified"}.get(decision)
    if not event:
        messages.error(request, "Invalid decision.")
        return redirect("/lead-manager/")
    if note:
        lead.notes = (lead.notes + "\n" if lead.notes else "") + f"[LM] {note}"
    lead.assigned_to = request.user
    lead.save()
    transition_lead(lead, event, actor=request.user)
    log(request.user, "lead.qualify", lead, request, decision=decision)
    messages.success(request, f"Lead marked {lead.get_stage_display()}.")
    return redirect("/lead-manager/")


@lead_manager_required
@require_POST
def lm_assign_inspection(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id)
    inspector_id = request.POST.get("inspector_id", "").strip()
    scheduled_at = request.POST.get("scheduled_at", "").strip()
    address = request.POST.get("inspection_address", "").strip() or lead.vehicle.inspection_address
    if not inspector_id or not scheduled_at:
        messages.error(request, "Select an inspector and a date/time.")
        return redirect("/lead-manager/")
    inspector = get_object_or_404(User, id=inspector_id, role=Role.INSPECTOR)

    visit, created = InspectionVisit.objects.get_or_create(
        lead=lead,
        defaults=dict(vehicle=lead.vehicle, inspector=inspector, assigned_by=request.user,
                      scheduled_at=scheduled_at, inspection_address=address,
                      status=InspectionVisit.Status.SCHEDULED),
    )
    if not created:
        visit.inspector = inspector
        visit.assigned_by = request.user
        visit.scheduled_at = scheduled_at
        visit.inspection_address = address
        visit.status = InspectionVisit.Status.SCHEDULED
        visit.save()

    lead.assigned_to = request.user
    lead.save()
    transition_lead(lead, "inspection_scheduled", actor=request.user)
    lead.vehicle.status = Vehicle.STATUS_INSPECTION
    lead.vehicle.inspection_address = address
    lead.vehicle.save()

    log(request.user, "lead.assign_inspector", lead, request, inspector_id=inspector.id)
    notify(inspector, "insp_assigned",
           title="New inspection assigned",
           body=f"{lead.vehicle} — scheduled {scheduled_at}", url="/")
    messages.success(request, "Inspection booked and assigned.")
    return redirect("/lead-manager/")


# ── Inspection staff calendar ────────────────────────────────────────────────

@lead_manager_required
def lm_calendar(request):
    inspectors = User.objects.filter(role=Role.INSPECTOR, is_suspended=False).order_by("username")
    legend = [{"name": (i.get_full_name() or i.username), "colour": _inspector_colour(i.id)}
              for i in inspectors]
    return render(request, "teams/lead_calendar.html", {"legend": legend})


@lead_manager_required
def lm_calendar_events(request):
    """FullCalendar event feed (filtered by the ?start/?end range it sends)."""
    qs = InspectionVisit.objects.select_related("vehicle", "inspector", "lead__seller")
    start, end = request.GET.get("start"), request.GET.get("end")
    if start and parse_datetime(start):
        qs = qs.filter(scheduled_at__gte=parse_datetime(start))
    if end and parse_datetime(end):
        qs = qs.filter(scheduled_at__lte=parse_datetime(end))

    events = []
    for v in qs:
        seller = _visit_seller(v)
        car = v.vehicle.display_name if v.vehicle else ""
        events.append({
            "id": v.id,
            "title": f"{seller} · {car}".strip(" ·"),
            "start": v.scheduled_at.isoformat() if v.scheduled_at else None,
            "end": (v.scheduled_at + timedelta(hours=1)).isoformat() if v.scheduled_at else None,
            "color": _inspector_colour(v.inspector_id),
            "url": f"/lead-manager/inspection/{v.id}/",
            "extendedProps": {
                "inspector": (v.inspector.get_full_name() or v.inspector.username) if v.inspector else "Unassigned",
                "seller": seller,
                "car": car,
                "address": v.inspection_address or "",
                "status": _STATUS_PILL.get(v.status, "Done"),
            },
        })
    return JsonResponse(events, safe=False)


@lead_manager_required
def lm_inspection_detail(request, visit_id):
    visit = get_object_or_404(
        InspectionVisit.objects.select_related("vehicle", "inspector", "lead__seller"), id=visit_id)
    report = getattr(visit, "report", None)
    return render(request, "teams/lead_inspection_detail.html", {
        "visit": visit, "report": report, "seller": _visit_seller(visit),
        "status_label": _STATUS_PILL.get(visit.status, "Done"),
    })
