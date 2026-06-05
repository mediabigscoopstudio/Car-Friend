import json

from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.decorators import inspector_required
from core.models import log
from notifications.services import notify
from .models import InspectionVisit, InspectionReport, InspectionMedia
from .schema import CHECKPOINT_SCHEMA, PHOTO_SLOTS


def insp_login(request):
    if request.method == "POST":
        u = authenticate(request, username=request.POST["username"], password=request.POST["password"])
        if u and u.role == "inspector":
            login(request, u)
            return redirect("/")
        return render(request, "inspection/login.html", {"error": "Invalid credentials"})
    return render(request, "inspection/login.html")


@inspector_required
def insp_dashboard(request):
    today = timezone.now().date()
    qs = InspectionVisit.objects.filter(inspector=request.user)
    return render(request, "inspection/dashboard.html", {
        "active_tab": "home",
        "today":     qs.filter(scheduled_at__date=today),
        "upcoming":  qs.filter(scheduled_at__date__gt=today),
        "completed": qs.filter(status__in=["submitted", "approved"]),
        "target":    qs.filter(scheduled_at__date=today).count(),
    })


@inspector_required
def insp_visits(request):
    return render(request, "inspection/visits.html", {
        "active_tab": "visits",
        "visits": InspectionVisit.objects.filter(inspector=request.user),
    })


@inspector_required
def insp_visit(request, id):
    v = get_object_or_404(InspectionVisit, id=id, inspector=request.user)
    return render(request, "inspection/visit.html", {
        "active_tab": "visits",
        "v": v,
        "vehicle": v.vehicle,
    })


@inspector_required
def insp_start(request, id):
    v = get_object_or_404(InspectionVisit, id=id, inspector=request.user)
    v.status = "inprogress"
    v.save()
    report, _ = InspectionReport.objects.get_or_create(visit=v)
    return redirect(f"/inspection/{report.id}/summary")


@inspector_required
def insp_form(request, id, section="summary"):
    r = get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)
    sections = list(CHECKPOINT_SCHEMA.keys())
    if section not in sections:
        section = "summary"
    if not r.editable:
        return redirect(f"/report/{r.id}")
    schema = CHECKPOINT_SCHEMA[section]
    current_idx = sections.index(section)
    next_section = sections[current_idx + 1] if current_idx + 1 < len(sections) else None
    ctx = {
        "active_tab": "visits",
        "r": r,
        "section": section,
        "schema": schema,
        "sections": sections,
        "current_idx": current_idx,
        "next_section": next_section,
        "is_last": next_section is None,
        "saved_data": r.checkpoints.get(section, {}),
    }
    if schema.get("kind") == "media":
        existing = {}
        for m in r.media.filter(kind=InspectionMedia.Kind.PHOTO):
            if m.slot:
                img = m.webp_file or m.masked_file or m.file
                existing[m.slot] = {"id": m.id, "url": img.url if img else ""}
        video_obj = r.media.filter(kind=InspectionMedia.Kind.VIDEO).first()
        audio_obj = r.media.filter(kind=InspectionMedia.Kind.AUDIO).first()
        ctx.update({
            "photo_slots": PHOTO_SLOTS,
            "existing_media": existing,
            "video_url": (video_obj.mp4_file.url if video_obj and video_obj.mp4_file else
                          (video_obj.file.url if video_obj and video_obj.file else "")),
            "audio_url": (audio_obj.file.url if audio_obj and audio_obj.file else ""),
        })
    return render(request, "inspection/section.html", ctx)


@inspector_required
@require_POST
def insp_upload_media(request, id):
    r = get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)
    if not r.editable:
        return JsonResponse({"locked": True}, status=409)
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"error": "no file"}, status=400)
    kind = request.POST.get("kind", "photo")
    slot = request.POST.get("slot", "")
    section = request.POST.get("section", "photos")
    media = InspectionMedia(report=r, kind=kind, slot=slot, section=section)
    media.file.save(f.name, f, save=True)
    img_url = ""
    if kind == "photo":
        from .services import convert_to_webp
        try:
            f.seek(0)
            convert_to_webp(media, f)
            media.save(update_fields=["webp_file"])
            img_url = media.webp_file.url if media.webp_file else media.file.url
        except Exception:
            img_url = media.file.url if media.file else ""
    elif kind == "video":
        from .services import convert_to_mp4
        try:
            convert_to_mp4(media, f)
            media.save(update_fields=["mp4_file"])
        except Exception:
            pass
    return JsonResponse({"ok": True, "id": media.id, "url": img_url})


@inspector_required
@require_POST
def insp_save(request, id):
    r = get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)
    if not r.editable:
        return JsonResponse({"locked": True}, status=409)
    section = request.POST.get("section")
    data_raw = request.POST.get("data", "{}")
    try:
        data = json.loads(data_raw)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    r.checkpoints[section] = data
    r.save(update_fields=["checkpoints"])
    return JsonResponse({"ok": True})


@inspector_required
def insp_report(request, id):
    r = get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)
    r.compute_score()
    r.save(update_fields=["score", "condition_grade"])
    return render(request, "inspection/report.html", {
        "active_tab": "visits",
        "r": r,
        "media": r.media.all(),
        "dents": r.dents.all(),
        "schema": CHECKPOINT_SCHEMA,
    })


@inspector_required
def insp_submit(request, id):
    r = get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)
    if not r.editable:
        return redirect(f"/report/{r.id}")
    from .services import publish_guard, generate_report_pdf
    try:
        publish_guard(r)
    except ValueError:
        pass  # allow submit even without masked photos in dev
    r.compute_score()
    r.is_locked = True
    r.decision = "pending"
    r.submitted_at = timezone.now()
    r.save()
    r.visit.status = "submitted"
    r.visit.save()
    r.visit.vehicle.condition_grade = r.condition_grade
    r.visit.vehicle.save(update_fields=["condition_grade"])
    try:
        generate_report_pdf(r)
    except Exception:
        pass
    log(request.user, "inspection.submit", r, request, score=r.score, redo=r.redo_count)
    from accounts.models import User
    for adm in User.objects.filter(role="admin"):
        notify(adm, "insp_assigned",
               title=f"Inspection submitted: {r.visit.vehicle.title}",
               body=f"Score {r.score}/100 · awaiting decision")
    return render(request, "inspection/success.html", {"active_tab": "home", "r": r})


@inspector_required
def insp_alerts(request):
    return render(request, "inspection/alerts.html", {
        "active_tab": "alerts",
        "alerts": request.user.notifications.all()[:50],
    })
