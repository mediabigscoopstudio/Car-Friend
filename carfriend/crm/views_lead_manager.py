"""Lead Manager role dashboard (teams host).

Role-scoped (lead_manager_required) — Lead Managers see only this dashboard and
the lead data; they triage incoming leads, qualify/un-qualify, and book an
inspection by assigning an Inspection Associate.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import lead_manager_required
from accounts.models import Role, User
from core.models import log
from crm.models import Lead
from inspections.models import InspectionVisit
from notifications.services import notify
from vehicles.models import Vehicle


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
    if decision == "qualified":
        lead.stage = Lead.STAGE_QUALIFIED
    elif decision == "unqualified":
        lead.stage = Lead.STAGE_UNQUALIFIED
    else:
        messages.error(request, "Invalid decision.")
        return redirect("/lead-manager/")
    if note:
        lead.notes = (lead.notes + "\n" if lead.notes else "") + f"[LM] {note}"
    lead.assigned_to = request.user
    lead.save()
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

    lead.stage = Lead.STAGE_INSP_SCHED
    lead.assigned_to = request.user
    lead.save()
    lead.vehicle.status = Vehicle.STATUS_INSPECTION
    lead.vehicle.inspection_address = address
    lead.vehicle.save()

    log(request.user, "lead.assign_inspector", lead, request, inspector_id=inspector.id)
    notify(inspector, "insp_assigned",
           title="New inspection assigned",
           body=f"{lead.vehicle} — scheduled {scheduled_at}", url="/")
    messages.success(request, "Inspection booked and assigned.")
    return redirect("/lead-manager/")
