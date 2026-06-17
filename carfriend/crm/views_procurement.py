"""Procurement Associate (teams host) — physical handover of cars AFTER a deal
is signed and payment is confirmed.

Single-purpose: handover queue, the per-deal checklist, and completed handovers.
A Procurement Associate sees NO leads, sellers, dealers, OCBs or auctions — only
payment-confirmed deals awaiting (or past) handover.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from deals.models import Deal, HandoverChecklist
from payments.models import Payment


def _require_procurement(request):
    if not request.user.is_authenticated:
        return redirect("/auth/login/")
    if request.user.role != User.ROLE_PROCUREMENT and not request.user.is_superuser:
        from accounts.views import get_dashboard_url
        return redirect(get_dashboard_url(request.user))
    return None


def _car(v):
    if not v:
        return "—"
    return f"{v.make} {v.model} {v.year}".strip()


def _queue_deals():
    """Deals with a CONFIRMED payment whose handover isn't completed yet.
    Payment-confirmed is the real signal; a completed handover has stock_out_at."""
    return (Deal.objects.filter(payments__status=Payment.Status.CONFIRMED)
            .exclude(handover__stock_out_at__isnull=False)
            .select_related("vehicle", "seller", "dealer")
            .distinct().order_by("-updated_at"))


def _queue_rows(deals):
    rows = []
    for d in deals:
        pay = d.payments.filter(status=Payment.Status.CONFIRMED).order_by("-confirmed_at").first()
        rows.append({
            "deal": d, "car": _car(d.vehicle),
            "seller": (d.seller.get_full_name() or d.seller.username) if d.seller else "—",
            "dealer": (d.dealer.get_full_name() or d.dealer.username) if d.dealer else "—",
            "plate": d.vehicle.plate_number if d.vehicle else "",
            "confirmed_at": pay.confirmed_at if pay else None,
        })
    return rows


# ── Dashboard ────────────────────────────────────────────────────────────────

def procurement_dashboard(request):
    guard = _require_procurement(request)
    if guard:
        return guard
    today, now = timezone.localdate(), timezone.now()
    rows = _queue_rows(_queue_deals())

    done = HandoverChecklist.objects.filter(stock_out_at__isnull=False).select_related("deal")
    hours = []
    for h in done:
        pay = h.deal.payments.filter(status=Payment.Status.CONFIRMED).order_by("confirmed_at").first()
        if pay and pay.confirmed_at and h.stock_out_at:
            hours.append((h.stock_out_at - pay.confirmed_at).total_seconds() / 3600)
    avg = round(sum(hours) / len(hours), 1) if hours else None

    stats = {
        "pending": len(rows),
        "completed_today": done.filter(stock_out_at__date=today).count(),
        "completed_month": done.filter(stock_out_at__year=now.year, stock_out_at__month=now.month).count(),
        "avg_hours": avg if avg is not None else "—",
    }
    return render(request, "teams/procurement/dashboard.html", {"stats": stats, "rows": rows[:5]})


# ── Handover queue ───────────────────────────────────────────────────────────

def procurement_queue(request):
    guard = _require_procurement(request)
    if guard:
        return guard
    rows = _queue_rows(_queue_deals())
    return render(request, "teams/procurement/queue.html", {"rows": rows})


# ── Handover detail / checklist ──────────────────────────────────────────────

def procurement_handover(request, deal_id):
    guard = _require_procurement(request)
    if guard:
        return guard
    deal = get_object_or_404(Deal.objects.select_related("vehicle", "seller", "dealer"), id=deal_id)
    pay = deal.payments.filter(status=Payment.Status.CONFIRMED).order_by("-confirmed_at").first()
    if not pay:
        messages.error(request, "Handover is only available for payment-confirmed deals.")
        return redirect("/crm/procurement/queue/")
    h, _ = HandoverChecklist.objects.get_or_create(deal=deal)
    completed = h.stock_out_at is not None

    if request.method == "POST" and not completed:
        h.keys_received = bool(request.POST.get("keys_received"))
        h.rc_received = bool(request.POST.get("rc_received"))
        h.insurance_received = bool(request.POST.get("insurance_received"))
        h.service_history_received = bool(request.POST.get("service_history_received"))
        h.notes = (request.POST.get("notes") or "").strip()
        if request.POST.get("action") == "complete":
            if not (h.keys_received and h.rc_received and h.insurance_received
                    and h.service_history_received):
                h.save()
                messages.error(request, "Tick all items before completing.")
                return redirect(f"/crm/procurement/handover/{deal.id}/")
            h.stock_out_at = timezone.now()
            h.completed_by = request.user
            h.save()
            deal.status = Deal.Status.CLOSED
            deal.save(update_fields=["status"])
            messages.success(request, "Handover completed — car marked stocked out.")
            return redirect("/crm/procurement/completed/")
        h.save()
        messages.success(request, "Progress saved.")
        return redirect(f"/crm/procurement/handover/{deal.id}/")

    return render(request, "teams/procurement/handover.html", {
        "deal": deal, "h": h, "pay": pay, "completed": completed,
        "car": _car(deal.vehicle),
        "seller": (deal.seller.get_full_name() or deal.seller.username) if deal.seller else "—",
        "dealer": (deal.dealer.get_full_name() or deal.dealer.username) if deal.dealer else "—",
    })


# ── Completed handovers ──────────────────────────────────────────────────────

def procurement_completed(request):
    guard = _require_procurement(request)
    if guard:
        return guard
    done = (HandoverChecklist.objects.filter(stock_out_at__isnull=False)
            .select_related("deal__vehicle", "deal__seller", "deal__dealer", "completed_by")
            .order_by("-stock_out_at"))
    rows = [{
        "h": h, "deal": h.deal, "car": _car(h.deal.vehicle),
        "seller": (h.deal.seller.get_full_name() or h.deal.seller.username) if h.deal.seller else "—",
        "dealer": (h.deal.dealer.get_full_name() or h.deal.dealer.username) if h.deal.dealer else "—",
    } for h in done]
    return render(request, "teams/procurement/completed.html", {"rows": rows})
