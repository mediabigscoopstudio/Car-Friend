from django.shortcuts import render, redirect, get_object_or_404

from accounts.decorators import admin_required
from core.models import log
from notifications.services import notify
from .models import InspectionReport
from .services import publish_guard


@admin_required
def inspection_queue(request):
    reports = (
        InspectionReport.objects
        .filter(visit__status="submitted")
        .select_related("visit__vehicle")
    )
    return render(request, "master/inspection_queue.html", {"reports": reports})


@admin_required
def inspection_review(request, id):
    r = get_object_or_404(InspectionReport, id=id)
    return render(
        request, "master/inspection_review.html",
        {"r": r, "media": r.media.all(), "dents": r.dents.all()},
    )


@admin_required
def inspection_decide(request, id):
    if request.method != "POST":
        return redirect("/inspection_queue")
    r = get_object_or_404(InspectionReport, id=id)
    decision = request.POST["decision"]
    r.decision_note = request.POST.get("note", "")
    r.decided_by = request.user
    v = r.visit
    if decision == "approve":
        publish_guard(r)
        v.status = "approved"
        v.vehicle.status = "approved"
        v.vehicle.save()
    elif decision == "reject":
        v.status = "rejected"
    else:
        v.status = "reinspect"
    v.save()
    r.save()
    log(request.user, "inspection.decide", r, request, decision=decision)
    if v.inspector:
        notify(
            v.inspector, "insp_decision",
            title=f"Inspection {decision}d: {v.vehicle.title}",
            body=r.decision_note,
        )
    return redirect("/inspection_queue")
