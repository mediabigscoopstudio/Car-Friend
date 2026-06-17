import json
import logging

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
from .schema import CHECKPOINT_SCHEMA

logger = logging.getLogger(__name__)


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
    qs = InspectionVisit.objects.filter(inspector=request.user).select_related('vehicle')
    # "pending" = today + overdue (any scheduled visit not yet submitted)
    pending   = qs.filter(status=InspectionVisit.Status.SCHEDULED)
    upcoming  = qs.filter(scheduled_at__date__gt=today).exclude(status=InspectionVisit.Status.SCHEDULED)
    completed = qs.filter(status__in=[InspectionVisit.Status.SUBMITTED, InspectionVisit.Status.APPROVED])
    inprogress = qs.filter(status=InspectionVisit.Status.INPROGRESS)
    return render(request, "inspection/dashboard.html", {
        "active_tab": "home",
        "pending":    pending,
        "upcoming":   upcoming,
        "completed":  completed,
        "inprogress": inprogress,
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
        photos, videos, audios = [], [], []
        for m in r.media.filter(kind=InspectionMedia.Kind.PHOTO):
            img = m.webp_file or m.masked_file or m.file
            if img:
                photos.append({"id": m.id, "url": img.url})
        for m in r.media.filter(kind=InspectionMedia.Kind.VIDEO):
            vid = m.mp4_file or m.file
            if vid:
                videos.append({"id": m.id, "url": vid.url})
        for m in r.media.filter(kind=InspectionMedia.Kind.AUDIO):
            if m.file:
                audios.append({"id": m.id, "url": m.file.url})
        ctx.update({"photos": photos, "videos": videos, "audios": audios})
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
    # Always persist the raw upload FIRST (to storage, not yet committed) so the
    # inspector's file is never lost even if conversion/transcode fails.
    media.file.save(f.name, f, save=False)

    if kind == "photo":
        from .services import convert_to_webp
        convert_to_webp(media, f)            # logs loudly + returns False on error; raw kept
    elif kind == "video":
        from .services import convert_to_mp4, is_web_ready_video
        if is_web_ready_video(f):
            pass                             # already MP4 → store as-is, no ffmpeg needed
        elif not convert_to_mp4(media, f):   # other format + ffmpeg missing/failed → keep raw
            media.needs_transcode = True
            logger.warning("TODO transcode: stored raw VIDEO for report %s (ffmpeg unavailable).", r.id)
    elif kind == "audio":
        from .services import convert_audio, is_web_ready_audio
        if is_web_ready_audio(f):
            pass                             # already mp3/m4a/aac → store as-is
        elif not convert_audio(media, f):
            media.needs_transcode = True
            logger.warning("TODO transcode: stored raw AUDIO for report %s (ffmpeg unavailable).", r.id)

    # Single commit: the record is never written without its file(s) on disk.
    media.save()

    if kind == "photo":
        img = media.webp_file or media.masked_file or media.file
        url = img.url if img else ""
    elif kind == "video":
        vid = media.mp4_file or media.file
        url = vid.url if vid else ""
    else:
        url = media.file.url if media.file else ""
    return JsonResponse({"ok": True, "id": media.id, "url": url,
                         "kind": kind, "needs_transcode": media.needs_transcode})


@inspector_required
@require_POST
def insp_delete_media(request, id):
    m = get_object_or_404(InspectionMedia, id=id, report__visit__inspector=request.user)
    if not m.report.editable:
        return JsonResponse({"locked": True}, status=409)
    m.delete()
    return JsonResponse({"ok": True})


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
