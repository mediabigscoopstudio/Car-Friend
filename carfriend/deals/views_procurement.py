"""Procurement Associate dashboard (teams host).

Role-scoped (procurement_required): cars in "payment confirmed" (Deal.PAID)
state — handover checklist, e-sign (stub) for both parties, and stock-out.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import procurement_required
from core.models import log
from deals import esign_service
from deals.models import Deal, DealAgreement, HandoverChecklist
from vehicles.models import Vehicle


def _items_for(deals):
    items = []
    for d in deals:
        handover, _ = HandoverChecklist.objects.get_or_create(deal=d)
        agreement, _ = DealAgreement.objects.get_or_create(deal=d)
        items.append({"deal": d, "handover": handover, "agreement": agreement})
    return items


@procurement_required
def proc_dashboard(request):
    paid = (Deal.objects.filter(status=Deal.Status.PAID)
            .select_related("vehicle", "seller", "dealer").order_by("-updated_at"))
    return render(request, "teams/procurement.html", {"items": _items_for(paid)})


@procurement_required
@require_POST
def proc_checklist(request, deal_id):
    deal = get_object_or_404(Deal, id=deal_id, status=Deal.Status.PAID)
    h, _ = HandoverChecklist.objects.get_or_create(deal=deal)
    h.keys_received = bool(request.POST.get("keys_received"))
    h.rc_received = bool(request.POST.get("rc_received"))
    h.insurance_received = bool(request.POST.get("insurance_received"))
    h.service_history_received = bool(request.POST.get("service_history_received"))
    h.notes = (request.POST.get("notes") or "").strip()
    h.save()
    log(request.user, "handover.checklist", deal, request)
    messages.success(request, "Handover checklist saved.")
    return redirect("/procurement/")


@procurement_required
@require_POST
def proc_esign(request, deal_id):
    deal = get_object_or_404(Deal, id=deal_id, status=Deal.Status.PAID)
    party = request.POST.get("party")
    if party not in ("seller", "dealer"):
        messages.error(request, "Invalid party.")
        return redirect("/procurement/")
    agreement, _ = DealAgreement.objects.get_or_create(deal=deal)
    ref = esign_service.sign_agreement(agreement, party)
    log(request.user, "deal.esign", deal, request, party=party, ref=ref)
    messages.success(request, f"{party.title()} e-signed the agreement (ref {ref}).")
    return redirect("/procurement/")


@procurement_required
@require_POST
def proc_stockout(request, deal_id):
    deal = get_object_or_404(Deal, id=deal_id, status=Deal.Status.PAID)
    h, _ = HandoverChecklist.objects.get_or_create(deal=deal)
    agreement, _ = DealAgreement.objects.get_or_create(deal=deal)
    if not h.all_received:
        messages.error(request, "Complete the handover checklist before stock-out.")
        return redirect("/procurement/")
    if not (agreement.seller_signed and agreement.dealer_signed):
        messages.error(request, "Both seller and dealer must e-sign before stock-out.")
        return redirect("/procurement/")
    h.stock_out_at = timezone.now()
    h.completed_by = request.user
    h.save()
    deal.status = Deal.Status.CLOSED
    deal.save(update_fields=["status"])
    deal.vehicle.status = Vehicle.STATUS_SOLD
    deal.vehicle.save(update_fields=["status"])
    log(request.user, "deal.stockout", deal, request)
    messages.success(request, "Car stocked out — handover complete.")
    return redirect("/procurement/")
