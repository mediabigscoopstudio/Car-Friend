"""Procurement Associate — handover only.

One purpose: complete vehicle handover for deals whose payment is confirmed.
Queue = confirmed-payment deals not yet stocked out. Completed = stocked out.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import procurement_required
from core.models import log
from deals.models import Deal, HandoverChecklist
from vehicles.models import Vehicle


@procurement_required
def proc_dashboard(request):
    """Handover queue: payment-confirmed deals not yet handed over."""
    paid = (Deal.objects.filter(status=Deal.Status.PAID)
            .select_related("vehicle", "seller", "dealer").order_by("-updated_at"))
    items = []
    for d in paid:
        h = getattr(d, "handover", None)
        if h and h.stock_out_at:
            continue  # already handed over
        pay = d.payments.filter(status="confirmed").order_by("-confirmed_at").first()
        items.append({"deal": d, "confirmed_at": pay.confirmed_at if pay else None})
    return render(request, "teams/procurement.html", {"items": items, "tab": "queue"})


@procurement_required
def proc_completed(request):
    done = (HandoverChecklist.objects.filter(stock_out_at__isnull=False)
            .select_related("deal__vehicle", "deal__seller", "deal__dealer", "completed_by")
            .order_by("-stock_out_at"))
    return render(request, "teams/procurement_completed.html", {"handovers": done, "tab": "completed"})


@procurement_required
def proc_handover(request, deal_id):
    deal = get_object_or_404(Deal.objects.select_related("vehicle", "seller", "dealer"), id=deal_id)
    h, _ = HandoverChecklist.objects.get_or_create(deal=deal)
    pay = deal.payments.filter(status="confirmed").order_by("-confirmed_at").first()
    return render(request, "teams/procurement_handover.html",
                  {"deal": deal, "h": h, "confirmed_at": pay.confirmed_at if pay else None})


@procurement_required
@require_POST
def proc_complete(request, deal_id):
    deal = get_object_or_404(Deal.objects.select_related("vehicle"), id=deal_id)
    h, _ = HandoverChecklist.objects.get_or_create(deal=deal)
    h.keys_received = bool(request.POST.get("keys_received"))
    h.rc_received = bool(request.POST.get("rc_received"))
    h.insurance_received = bool(request.POST.get("insurance_received"))
    h.service_history_received = bool(request.POST.get("service_history_received"))
    h.notes = (request.POST.get("notes") or "").strip()

    if not h.all_received:
        h.save()
        messages.error(request, "Tick all four checklist items before completing the handover.")
        return redirect(f"/procurement/{deal.id}/")

    h.stock_out_at = timezone.now()
    h.completed_by = request.user
    h.save()
    deal.status = Deal.Status.CLOSED
    deal.save(update_fields=["status"])
    deal.vehicle.status = Vehicle.STATUS_SOLD
    deal.vehicle.save(update_fields=["status"])
    lead = getattr(deal.vehicle, "lead", None)
    if lead and lead.stage != lead.STAGE_CLOSED:
        lead.stage = lead.STAGE_CLOSED
        lead.save(update_fields=["stage"])
    log(request.user, "handover.complete", deal, request)
    messages.success(request, "Handover completed — car stocked out.")
    return redirect("/procurement/")
