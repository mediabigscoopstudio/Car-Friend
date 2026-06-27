import json
import logging
import os
import uuid

from django.contrib.auth import authenticate, login
from django.core.files.base import ContentFile
from django.db import models
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.decorators import inspector_required
from core.models import log
from notifications.services import notify
from .models import InspectionVisit, InspectionReport, InspectionMedia, CheckpointPhoto
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


# ---------------------------------------------------------------------------
# v4 inspector shell — shared helpers
# ---------------------------------------------------------------------------
def _greeting():
    h = timezone.localtime().hour
    if h < 12:  return "Good morning"
    if h < 17:  return "Good afternoon"
    return "Good evening"


def _shell(request, **extra):
    """Context every v4 shell screen needs (bell unread dot, greeting)."""
    ctx = {
        "greeting": _greeting(),
        "unread_count": request.user.notifications.filter(is_read=False).count(),
    }
    ctx.update(extra)
    return ctx


def _report_for(visit):
    return InspectionReport.objects.filter(visit=visit).first()


def _progress(report):
    """Rough resolved-progress for the resume hero until the zone engine lands
    (Phase 4). Counts schema sections that have any saved checkpoint data."""
    if not report or not report.checkpoints:
        return {"pct": 0, "done": 0, "total": len(CHECKPOINT_SCHEMA)}
    total = len(CHECKPOINT_SCHEMA)
    done = sum(1 for k in CHECKPOINT_SCHEMA if report.checkpoints.get(k))
    return {"pct": round(done * 100 / total) if total else 0, "done": done, "total": total}


@inspector_required
def insp_dashboard(request):
    today = timezone.now().date()
    qs = InspectionVisit.objects.filter(inspector=request.user).select_related('vehicle')
    S = InspectionVisit.Status
    pending    = qs.filter(status=S.SCHEDULED)
    upcoming   = qs.filter(scheduled_at__date__gt=today).exclude(status=S.SCHEDULED)
    completed  = qs.filter(status__in=[S.SUBMITTED, S.APPROVED])
    inprogress = qs.filter(status=S.INPROGRESS)

    # Approval pill (§4.1): approved vs rejected of everything reviewed.
    approved = qs.filter(status=S.APPROVED).count()
    rejected = qs.filter(status__in=[S.REJECTED, S.REINSPECT]).count()
    reviewed = approved + rejected
    approval_rate = round(approved * 100 / reviewed) if reviewed else 100

    # Resume hero: most recent in-progress inspection, else the next scheduled job.
    resume = inprogress.order_by('-updated_at').first()
    resume_ctx = None
    if resume:
        rep = _report_for(resume)
        resume_ctx = {"visit": resume, "report": rep, "progress": _progress(rep)}
    next_job = pending.order_by('scheduled_at').first()

    return render(request, "inspection/home.html", _shell(request,
        active_tab="home",
        stats={"assigned": pending.count() + inprogress.count(),
               "pending": pending.count(), "done": completed.count()},
        approval={"rate": approval_rate, "approved": approved, "rejected": rejected},
        resume=resume_ctx,
        next_job=next_job,
    ))


@inspector_required
def insp_jobs(request):
    qs = InspectionVisit.objects.filter(inspector=request.user).select_related('vehicle')
    S = InspectionVisit.Status
    tab = request.GET.get("tab", "pending")
    q = (request.GET.get("q") or "").strip()
    pending_qs   = qs.filter(status__in=[S.SCHEDULED, S.INPROGRESS, S.REINSPECT])
    completed_qs = qs.filter(status__in=[S.SUBMITTED, S.APPROVED, S.REJECTED])
    rows = (completed_qs if tab == "completed" else pending_qs).order_by('scheduled_at')
    if q:
        rows = rows.filter(
            models.Q(vehicle__make__icontains=q) | models.Q(vehicle__model__icontains=q)
            | models.Q(vehicle__plate_number__icontains=q) | models.Q(lead__name__icontains=q)
        )
    return render(request, "inspection/jobs.html", _shell(request,
        active_tab="jobs", tab=tab, q=q, rows=rows,
        pending_count=pending_qs.count(), completed_count=completed_qs.count(),
    ))


@inspector_required
def insp_schedule(request):
    # Phase 1: routed real screen (a simple grouped agenda). The full month
    # calendar + day bottom sheet lands in Phase 3.
    qs = (InspectionVisit.objects.filter(inspector=request.user)
          .select_related('vehicle').order_by('scheduled_at'))
    return render(request, "inspection/schedule.html", _shell(request,
        active_tab="schedule", visits=qs))


@inspector_required
def insp_profile(request):
    return render(request, "inspection/profile.html", _shell(request,
        pushed=True, hide_nav=True, back_url="/", visits_done=
        InspectionVisit.objects.filter(inspector=request.user,
            status=InspectionVisit.Status.APPROVED).count()))


@inspector_required
def insp_notifications(request):
    notes = request.user.notifications.all()[:60]
    return render(request, "inspection/notifications.html", _shell(request,
        pushed=True, hide_nav=True, back_url="/", notes=notes))


@inspector_required
@require_POST
def insp_notifications_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect("/notifications")


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
    elif schema.get("parts"):
        # Condition photos per checkpoint (section + part key), for this section.
        cp = {}
        for ph in r.checkpoint_photos.filter(section=section):
            cp.setdefault(ph.checkpoint_key, []).append({"id": ph.id, "url": ph.image.url})
        ctx["checkpoint_photos"] = cp
    return render(request, "inspection/section.html", ctx)


@inspector_required
@require_POST
def insp_checkpoint_photo(request, id):
    """Upload one condition photo for a checkpoint (section + checkpoint_key),
    converted to WebP like the rest of the inspection media."""
    r = get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)
    if not r.editable:
        return JsonResponse({"locked": True}, status=409)
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"error": "no file"}, status=400)
    section = request.POST.get("section", "")
    key = request.POST.get("checkpoint_key", "")
    # Validate the checkpoint belongs to this inspection's schema.
    schema = CHECKPOINT_SCHEMA.get(section)
    valid_keys = {p["key"] for p in schema.get("parts", [])} if schema else set()
    if not key or key not in valid_keys:
        return JsonResponse({"error": "bad checkpoint"}, status=400)

    from .services import image_to_webp_bytes
    photo = CheckpointPhoto(report=r, section=section, checkpoint_key=key)
    data = image_to_webp_bytes(f)
    if data is not None:
        photo.image.save(f"{uuid.uuid4().hex}.webp", ContentFile(data), save=False)
    else:
        # Conversion failed (rare) — keep the raw image so nothing is lost.
        ext = os.path.splitext(f.name)[1].lower() or ".jpg"
        photo.image.save(f"{uuid.uuid4().hex}{ext}", f, save=False)
    photo.save()
    return JsonResponse({"ok": True, "id": photo.id, "url": photo.image.url})


@inspector_required
@require_POST
def insp_checkpoint_photo_delete(request, photo_id):
    photo = get_object_or_404(
        CheckpointPhoto, id=photo_id, report__visit__inspector=request.user
    )
    if not photo.report.editable:
        return JsonResponse({"locked": True}, status=409)
    photo.delete()
    return JsonResponse({"ok": True})


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
    # Short, safe storage name — the raw upload name can be huge/unsafe and
    # tripped SuspiciousFileOperation. uuid + original extension only.
    ext = os.path.splitext(f.name)[1].lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    media = InspectionMedia(report=r, kind=kind, slot=slot, section=section)

    if kind == "video":
        # DECOUPLED: save the raw upload as-is and return immediately. NO ffmpeg
        # in the request — compression runs later via the management command
        # `transcode_pending_videos` (manually or by cron). The raw mp4 is a
        # valid, playable file, so it's viewable while it waits to be compressed.
        media.file.save(safe_name if ext else f"{safe_name}.mp4", f, save=False)
        media.needs_transcode = True
        media.transcoded = False
    elif kind == "photo":
        media.file.save(safe_name, f, save=False)
        from .services import convert_to_webp
        convert_to_webp(media, f)            # logs loudly + returns False on error; raw kept
    elif kind == "audio":
        media.file.save(safe_name, f, save=False)
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
    # Condition photos grouped by checkpoint (in schema order), for the report.
    by_key = {}
    for ph in r.checkpoint_photos.all():
        by_key.setdefault((ph.section, ph.checkpoint_key), []).append(ph.image.url)
    checkpoint_photo_groups = []
    for sec_key, sec in CHECKPOINT_SCHEMA.items():
        for part in sec.get("parts", []):
            urls = by_key.get((sec_key, part["key"]))
            if urls:
                checkpoint_photo_groups.append({
                    "section": sec.get("label", sec_key),
                    "label": part["label"],
                    "urls": urls,
                })
    return render(request, "inspection/report.html", {
        "active_tab": "visits",
        "r": r,
        "media": r.media.all(),
        "dents": r.dents.all(),
        "schema": CHECKPOINT_SCHEMA,
        "checkpoint_photo_groups": checkpoint_photo_groups,
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
    # Challan snapshot from Surepass (synchronous, 15s timeout). Fully isolated:
    # a challan API failure must NEVER break submission — store status=failed.
    try:
        from www.services import fetch_challans
        v = r.visit.vehicle
        res = fetch_challans(v.plate_number, chassis=v.chassis_number, engine=v.engine_number)
        r.challan_data = res["challans"]
        r.challan_count = res["total_challans"]
        r.challan_total_pending = res["total_pending_amount"]
        r.challan_fetch_status = res["status"]
        r.challan_fetched_at = timezone.now()
        r.save(update_fields=["challan_data", "challan_count", "challan_total_pending",
                              "challan_fetch_status", "challan_fetched_at"])
    except Exception:
        logger.exception("Challan fetch failed during submit for report %s", r.id)
        try:
            r.challan_fetch_status = "failed"
            r.challan_fetched_at = timezone.now()
            r.save(update_fields=["challan_fetch_status", "challan_fetched_at"])
        except Exception:
            pass
    try:
        generate_report_pdf(r)
    except Exception:
        pass
    log(request.user, "inspection.submit", r, request, score=r.score, redo=r.redo_count)
    from accounts.models import User
    for adm in User.objects.filter(role="admin"):
        notify(adm, "insp_assigned",
               title=f"Inspection submitted: {r.visit.vehicle.display_name}",
               body=f"Score {r.score}/100 · awaiting decision")
    return render(request, "inspection/success.html", {"active_tab": "home", "r": r})


@inspector_required
def insp_alerts(request):
    return render(request, "inspection/alerts.html", {
        "active_tab": "alerts",
        "alerts": request.user.notifications.all()[:50],
    })
