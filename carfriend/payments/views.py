from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.decorators import admin_required
from core.models import log
from notifications.services import notify
from .models import Payment


@admin_required
def payments_pending(request):
    return render(
        request, "master/payments.html",
        {"active": "payments", "payments": Payment.objects.filter(status="pending")},
    )


@admin_required
def payment_confirm(request, id):
    p = get_object_or_404(Payment, id=id)
    if request.method == "POST":
        if "proof_image" in request.FILES:
            p.proof_image = request.FILES["proof_image"]
        p.status = "confirmed"
        p.confirmed_by = request.user
        p.confirmed_at = timezone.now()
        p.note = request.POST.get("note", "")
        p.save()
        d = p.deal
        d.status = "paid"
        d.save(update_fields=["status"])
        log(request.user, "payment.confirm", p, request, amount=p.amount)
        notify(d.seller, "payment_ok",
               title="Payment confirmed",
               body=f"₹{p.amount:,} for {d.vehicle.title}")
        notify(d.dealer, "payment_ok",
               title="Payment confirmed",
               body=f"₹{p.amount:,} for {d.vehicle.title}")
        # Notify Procurement Associates that the car is ready for handover.
        from accounts.models import Role, User
        for proc_user in User.objects.filter(role=Role.PROCUREMENT, is_suspended=False):
            notify(proc_user, "payment_ok",
                   title="Handover ready",
                   body=f"Payment confirmed for {d.vehicle} — ready for handover.",
                   url="/procurement/")
        return redirect("/payments_pending")
    return render(request, "master/payment_confirm.html", {"active": "payments", "p": p})
