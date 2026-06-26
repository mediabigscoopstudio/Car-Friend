"""Single, atomic code path for assigning (and re-assigning) an inspector to a
lead.

Every assign/reassign surface (teams pipeline, lead-manager, master) funnels
through `assign_inspector_to_lead` so the four steps that previously drifted
apart always happen together, or not at all:

  (a) set/update the inspector FK on the lead's InspectionVisit,
  (b) create/link the inspector-facing visit record the inspector dashboard
      reads (InspectionVisit, filtered by `inspector` + status SCHEDULED),
  (c) advance the lead via the pipeline state machine (New -> Inspection
      Scheduled), forward-only so a reassign never regresses the stage,
  (d) write an audit row.

Because the visit is OneToOne with the lead, updating its `inspector` FK
atomically moves the job off the old inspector's dashboard and onto the new
one — no orphaned/duplicate records.
"""

from django.db import transaction

from accounts.models import Role, User
from inspections.models import InspectionVisit


def inspectors_for_vehicle(vehicle):
    """Active inspectors, preferring those in the vehicle's city. Falls back to
    all inspectors when no local match exists, so assignment is never blocked."""
    base = (User.objects.filter(role=Role.INSPECTOR, is_active=True, is_suspended=False)
            .order_by("first_name", "username"))
    city = (getattr(vehicle, "city", "") or "").strip()
    if city:
        local = base.filter(city__iexact=city)
        if local.exists():
            return local
    return base


@transaction.atomic
def assign_inspector_to_lead(lead, inspector, *, scheduled_at, address, actor=None, request=None):
    """Atomically (re)assign `inspector` to `lead`. Returns (visit, previous_inspector)."""
    from crm.services import transition_lead
    from core.models import log
    from vehicles.models import Vehicle

    # Lock the existing visit row (if any) so concurrent assigns can't race.
    visit = InspectionVisit.objects.select_for_update().filter(lead=lead).first()
    previous = visit.inspector if visit else None

    if visit is None:
        visit = InspectionVisit(lead=lead, vehicle=lead.vehicle)
    visit.inspector = inspector
    visit.assigned_by = actor
    visit.scheduled_at = scheduled_at
    visit.inspection_address = address
    visit.status = InspectionVisit.Status.SCHEDULED
    visit.save()

    # Keep the vehicle in step (mirrors the prior inline behaviour).
    if lead.vehicle:
        lead.vehicle.status = Vehicle.STATUS_INSPECTION
        lead.vehicle.inspection_address = address
        lead.vehicle.save(update_fields=["status", "inspection_address", "updated_at"])

    # Forward-only: first assign moves New -> Inspection Scheduled (and audits via
    # LeadStatusEvent); a reassign is a no-op here, so the stage never regresses.
    transition_lead(lead, "inspection_scheduled", actor=actor)

    reassigned = previous is not None and previous.id != inspector.id
    log(actor, "lead.reassign_inspector" if reassigned else "lead.assign_inspector",
        lead, request, inspector_id=inspector.id,
        previous_inspector_id=previous.id if previous else None)

    return visit, previous
