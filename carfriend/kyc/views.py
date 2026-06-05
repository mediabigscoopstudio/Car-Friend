from django.shortcuts import render, redirect, get_object_or_404

from accounts.decorators import admin_required
from core.models import log
from notifications.services import notify
from .models import KYCVerification


@admin_required
def kyc_queue(request):
    return render(
        request, "master/kyc_queue.html",
        {"active": "users", "records": KYCVerification.objects.filter(status="pending")},
    )


@admin_required
def kyc_decide(request, id):
    if request.method != "POST":
        return redirect("/kyc_queue")
    rec = get_object_or_404(KYCVerification, id=id)
    rec.status = request.POST["decision"]
    rec.reviewed_by = request.user
    rec.note = request.POST.get("note", "")
    rec.save()
    log(request.user, "kyc.decide", rec, request, status=rec.status)
    notify(
        rec.subject, "kyc_result",
        title=f"{rec.get_kind_display()} {rec.status}",
        body=rec.note,
    )
    return redirect("/kyc_queue")
