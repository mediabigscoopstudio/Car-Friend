"""Retail Associate dashboard (teams host) — Lead Pipeline only + OCB creation.

Role-scoped (retail_required). Nav is restricted to the lead pipeline and the
Retail Associate's own OCB tasks.
"""

from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from accounts.decorators import retail_required
from auctions.models import OCBListing
from crm.models import Lead

# The 8 pipeline columns (un-qualified is handled by the Lead Manager, not shown
# on the Retail board).
RETAIL_STAGES = [
    Lead.STAGE_NEW, Lead.STAGE_QUALIFIED, Lead.STAGE_INSP_SCHED, Lead.STAGE_INSP_DONE,
    Lead.STAGE_APPROVED, Lead.STAGE_NEGOTIATION, Lead.STAGE_AUCTION, Lead.STAGE_CLOSED,
]
_LABELS = dict(Lead.STAGE_CHOICES)


@retail_required
def retail_pipeline(request):
    leads = list(Lead.objects.select_related("vehicle", "seller"))
    now = timezone.now()
    columns = []
    for stage in RETAIL_STAGES:
        cards = []
        for l in leads:
            if l.stage != stage:
                continue
            v = l.vehicle
            cards.append({
                "id": l.id,
                "seller": (l.seller.get_full_name() or l.seller.username) if l.seller else "—",
                "car": v.display_name if v else "—",
                "year": v.year if v else "",
                "price": v.expected_price if v else None,
                "days": (now - l.updated_at).days,
            })
        columns.append({"label": _LABELS.get(stage, stage), "count": len(cards), "cards": cards})
    return render(request, "teams/retail_pipeline.html", {"columns": columns})


@retail_required
def retail_lead_detail(request, lead_id):
    lead = get_object_or_404(Lead.objects.select_related("vehicle", "seller"), id=lead_id)
    can_ocb = lead.stage in (Lead.STAGE_NEGOTIATION, Lead.STAGE_AUCTION)
    existing_ocb = (OCBListing.objects.filter(vehicle=lead.vehicle).order_by("-created_at").first()
                    if lead.vehicle else None)
    return render(request, "teams/retail_lead_detail.html", {
        "lead": lead, "can_ocb": can_ocb, "existing_ocb": existing_ocb,
    })
