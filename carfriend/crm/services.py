"""Lead pipeline state machine.

`transition_lead` is the ONLY place `Lead.stage` is allowed to change. Status is
a read-only reflection of real domain actions: views call this with an *event*
(what actually happened) rather than setting a stage directly. Every applied
transition writes a `LeadStatusEvent` audit row, and transitions are idempotent
and forward-only (re-firing the same event, or a stale earlier event, is a
no-op) so the pipeline can never double-advance or drift backward.
"""

from crm.models import Lead, LeadStatusEvent


# event (real action) -> resulting stage
EVENT_STAGE = {
    "created":               Lead.STAGE_NEW,
    "qualified":             Lead.STAGE_QUALIFIED,
    "unqualified":           Lead.STAGE_UNQUALIFIED,
    "inspection_scheduled":  Lead.STAGE_INSP_SCHED,
    "inspection_started":    Lead.STAGE_INSP_PROG,
    "report_submitted":      Lead.STAGE_INSP_DONE,
    "admin_approved":        Lead.STAGE_APPROVED,
    "allocated":             Lead.STAGE_ASSIGNED,
    "auction_created":       Lead.STAGE_AUCTION,
    "auction_live":          Lead.STAGE_AUCTION_LIVE,
    "auction_closed":        Lead.STAGE_AUCTION_CLOSED,
    "seller_approved":       Lead.STAGE_SELLER_APPROVED,
    "ocb_requested":         Lead.STAGE_OCB,
    "agreement_signed":      Lead.STAGE_AGREEMENT,
    "handed_to_procurement": Lead.STAGE_PROCUREMENT,
    "closed":                Lead.STAGE_CLOSED,
}

# Linear rank used to enforce forward-only progress. Parallel/branch stages share
# a rank so neither blocks the other (e.g. seller-approved vs ocb-in-progress, or
# qualified vs unqualified). A transition applies only when it strictly advances.
STAGE_RANK = {
    Lead.STAGE_NEW:             0,
    Lead.STAGE_QUALIFIED:       10,
    Lead.STAGE_UNQUALIFIED:     10,
    Lead.STAGE_INSP_SCHED:      20,
    Lead.STAGE_INSP_PROG:       30,
    Lead.STAGE_INSP_DONE:       40,
    Lead.STAGE_APPROVED:        50,
    Lead.STAGE_ASSIGNED:        60,
    Lead.STAGE_AUCTION:         70,
    Lead.STAGE_AUCTION_LIVE:    80,
    Lead.STAGE_AUCTION_CLOSED:  90,
    Lead.STAGE_NEGOTIATION:     95,
    Lead.STAGE_SELLER_APPROVED: 100,
    Lead.STAGE_OCB:             100,
    Lead.STAGE_AGREEMENT:       110,
    Lead.STAGE_PROCUREMENT:     120,
    Lead.STAGE_CLOSED:          130,
}


def transition_lead(lead, event, *, actor=None, to_stage=None):
    """Advance `lead` in response to a domain `event`.

    Returns the `LeadStatusEvent` that was written, or None if the event was a
    no-op (idempotent re-fire, stale/backward event, or unknown event). Safe to
    call with `lead=None` (no-op) so callers don't have to guard.

    `event="manual_override"` (admin-only) bypasses the forward-only guard and
    moves the lead to the explicit `to_stage`.
    """
    if lead is None:
        return None

    if event == "manual_override":
        target = to_stage
        if target not in dict(Lead.STAGE_CHOICES):
            return None
        force = True
    else:
        target = EVENT_STAGE.get(event)
        if target is None:
            return None
        force = False

    current = lead.stage
    if current == target:
        return None  # idempotent
    if not force:
        if STAGE_RANK.get(target, -1) <= STAGE_RANK.get(current, -1):
            return None  # stale / backward event — ignore

    from_status = current
    lead.stage = target
    lead.save(update_fields=["stage", "updated_at"])
    return LeadStatusEvent.objects.create(
        lead=lead,
        from_status=from_status,
        to_status=target,
        trigger=event,
        actor=actor,
    )


def transition_lead_for_vehicle(vehicle, event, *, actor=None, to_stage=None):
    """Convenience: resolve the Lead from a Vehicle (1-to-1) and transition it.
    Used by OCB/auction code paths that hold a vehicle, not a lead."""
    lead = Lead.objects.filter(vehicle=vehicle).first()
    return transition_lead(lead, event, actor=actor, to_stage=to_stage)
