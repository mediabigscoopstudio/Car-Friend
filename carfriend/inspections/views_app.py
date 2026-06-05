from django.contrib.auth import authenticate, login
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.decorators import inspector_required
from core.models import log
from notifications.services import notify
from .models import InspectionVisit, InspectionReport, SECTIONS
from .services import generate_pdf, publish_guard


def insp_login(request):
    if request.method == "POST":
        u = authenticate(
            request,
            username=request.POST["username"],
            password=request.POST["password"],
        )
        if u and u.role == "inspector":
            login(request, u)
            return redirect("/visits")
        return render(request, "inspection/login.html", {"error": "Invalid credentials"})
    return render(request, "inspection/login.html")


@inspector_required
def insp_dashboard(request):
    today = timezone.now().date()
    qs = InspectionVisit.objects.filter(inspector=request.user)
    return render(request, "inspection/dashboard.html", {
        "today":     qs.filter(scheduled_at__date=today),
        "upcoming":  qs.filter(scheduled_at__date__gt=today),
        "completed": qs.filter(status__in=["submitted", "approved"]),
        "target":    qs.filter(scheduled_at__date=today).count(),
    })


@inspector_required
def insp_visits(request):
    return render(
        request, "inspection/visits.html",
        {"visits": InspectionVisit.objects.filter(inspector=request.user)},
    )


@inspector_required
def insp_visit(request, id):
    v = get_object_or_404(InspectionVisit, id=id, inspector=request.user)
    return render(request, "inspection/visit.html", {"v": v, "vehicle": v.vehicle})


@inspector_required
def insp_start(request, id):
    v = get_object_or_404(InspectionVisit, id=id, inspector=request.user)
    v.status = "inprogress"
    v.save()
    report, _ = InspectionReport.objects.get_or_create(visit=v)
    return redirect(f"/inspection/{report.id}/basic")


@inspector_required
def insp_form(request, id, section):
    r = get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)
    if section not in SECTIONS:
        section = "basic"
    if request.method == "POST":
        sec_data = r.checkpoints.setdefault(section, {})
        for key, val in request.POST.items():
            if key.startswith("cp_"):
                cp_key = key[3:]
                sev = int(request.POST.get(f"sev_{cp_key}", 0))
                sec_data[cp_key] = {"val": val, "sev": sev}
        r.is_synced = True
        r.save(update_fields=["checkpoints", "is_synced"])
        current_idx = SECTIONS.index(section)
        if current_idx + 1 < len(SECTIONS):
            return redirect(f"/inspection/{id}/{SECTIONS[current_idx + 1]}")
        return redirect(f"/report/{id}")

    done = sum(len(s) for s in r.checkpoints.values())
    issues = sum(
        1 for s in r.checkpoints.values()
        for it in s.values() if int(it.get("sev", 0)) > 0
    )
    from .checkpoints import CHECKPOINT_MAP

    return render(request, f"inspection/section_{section}.html", {
        "r":                 r,
        "section":           section,
        "done":              done,
        "issues":            issues,
        "sections":          SECTIONS,
        "section_data":      r.checkpoints.get(section, {}),
        "preset_checkpoints": CHECKPOINT_MAP.get(section, []),
    })


@inspector_required
def insp_report(request, id):
    r = get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)
    r.compute_score()
    r.save()
    return render(request, "inspection/report.html", {
        "r": r, "media": r.media.all(), "dents": r.dents.all(),
    })


@inspector_required
def insp_submit(request, id):
    r = get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)
    publish_guard(r)
    r.compute_score()
    v = r.visit.vehicle
    v.condition_grade = r.condition_grade
    v.est_market_value = r.est_market_value or r.score * 10000
    v.save()
    r.submitted_at = timezone.now()
    r.save()
    r.visit.status = "submitted"
    r.visit.save()
    generate_pdf(r)
    log(request.user, "inspection.submit", r, request, score=r.score)
    from accounts.models import User
    for adm in User.objects.filter(role="admin"):
        notify(
            adm, "insp_assigned",
            title=f"Inspection submitted: {r.visit.vehicle.title}",
            body=f"Score {r.score}/100 · awaiting approval",
        )
    return render(request, "inspection/success.html", {"r": r})


@inspector_required
def insp_alerts(request):
    return render(
        request, "inspection/alerts.html",
        {"alerts": request.user.notifications.all()[:50]},
    )
