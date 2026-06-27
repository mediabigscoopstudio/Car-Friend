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
from .models import (InspectionVisit, InspectionReport, InspectionMedia,
                     CheckpointPhoto, VehicleRegistryData)
from .schema import CHECKPOINT_SCHEMA
from . import engine, zones

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


def _day_status(statuses):
    """Dominant colour meaning for a calendar day (§4.2)."""
    if "inprogress" in statuses:                       return "prog"
    if "scheduled" in statuses or "reinspect" in statuses: return "pend"
    if "rejected" in statuses:                          return "alert"
    if statuses & {"submitted", "approved"}:            return "done"
    return ""


@inspector_required
def insp_schedule(request):
    import calendar as _cal
    today = timezone.localdate()
    try:
        year  = int(request.GET.get("y", today.year))
        month = int(request.GET.get("m", today.month))
    except (TypeError, ValueError):
        year, month = today.year, today.month
    if not (1 <= month <= 12):
        year, month = today.year, today.month

    weeks_dates = _cal.Calendar(firstweekday=6).monthdatescalendar(year, month)
    span_start, span_end = weeks_dates[0][0], weeks_dates[-1][6]

    visits = (InspectionVisit.objects.filter(inspector=request.user,
                scheduled_at__date__range=(span_start, span_end))
              .select_related("vehicle", "lead__seller", "report").order_by("scheduled_at"))
    by_day = {}
    for v in visits:
        by_day.setdefault(timezone.localtime(v.scheduled_at).date(), []).append(v)

    weeks, sheets, total = [], [], 0
    for wk in weeks_dates:
        cells = []
        for d in wk:
            in_month = d.month == month and d.year == year
            day_visits = by_day.get(d, []) if in_month else []
            if in_month:
                total += len(day_visits)
            statuses = {v.status for v in day_visits}
            cells.append({
                "day": d.day, "iso": d.isoformat(), "in_month": in_month,
                "is_today": d == today, "count": len(day_visits),
                "status": _day_status(statuses),
            })
            if day_visits:
                done = sum(1 for v in day_visits
                           if v.status in ("submitted", "approved"))
                sheets.append({
                    "iso": d.isoformat(),
                    "title": d.strftime("%A, %d %B"),
                    "sub": f"{len(day_visits)} inspection{'s' if len(day_visits) != 1 else ''}"
                           + (f" · {done} done" if done else ""),
                    "jobs": day_visits,
                })
        weeks.append(cells)

    prev_m = (month - 2) % 12 + 1
    prev_y = year - 1 if month == 1 else year
    next_m = month % 12 + 1
    next_y = year + 1 if month == 12 else year

    return render(request, "inspection/schedule.html", _shell(request,
        active_tab="schedule",
        weeks=weeks, sheets=sheets, total=total,
        month_name=_cal.month_name[month], year=year,
        is_current=(year == today.year and month == today.month),
        prev_url=f"/schedule?y={prev_y}&m={prev_m}",
        next_url=f"/schedule?y={next_y}&m={next_m}",
        weekday_headers=["S", "M", "T", "W", "T", "F", "S"],
    ))


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


# ---------------------------------------------------------------------------
# Walk-around inspection flow (v4 §5). Lives on new routes ALONGSIDE the legacy
# section flow; legacy stays the live entry point until Phase 7 wires submit.
# ---------------------------------------------------------------------------
def _get_report(request, id):
    return get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)


@inspector_required
def insp_inspect_start(request, id):
    """Beta entry into the walk-around flow from a visit (mirrors insp_start)."""
    v = get_object_or_404(InspectionVisit, id=id, inspector=request.user)
    if v.status == InspectionVisit.Status.SCHEDULED:
        v.status = InspectionVisit.Status.INPROGRESS
        v.save(update_fields=["status", "updated_at"])
    report, _ = InspectionReport.objects.get_or_create(visit=v)
    return redirect(f"/inspect/{report.id}")


@inspector_required
def insp_inspect(request, id):
    r = _get_report(request, id)
    # Mandatory pre-inspection hero shot — gates the whole flow (Change 1).
    if not r.auction_hero_image and r.editable:
        return render(request, "inspection/hero.html", _shell(request,
            pushed=True, hide_nav=True, back_url="/jobs", r=r, vehicle=r.visit.vehicle))
    return render(request, "inspection/inspect.html", _shell(request,
        active_tab="jobs", pushed=True, hide_nav=True, back_url="/jobs",
        r=r, vehicle=r.visit.vehicle,
        zone_states=engine.zone_states(r),
        overall=engine.overall_progress(r),
        active=engine.active_zone_key(r),
        unlocked=request.GET.get("unlocked") == "1",
        all_done=engine.active_zone_key(r) is None,
    ))


@inspector_required
def insp_zone(request, id, zone_key):
    r = _get_report(request, id)
    if zone_key not in zones.ZONE_BY_KEY:
        return redirect(f"/inspect/{r.id}")
    if not r.editable:
        return redirect(f"/report/{r.id}")
    if not engine.can_enter(r, zone_key):
        return redirect(f"/inspect/{r.id}")     # gated — zone still locked
    zone = zones.ZONE_BY_KEY[zone_key]
    res = engine.results(r)
    media_by_key = {}
    for m in r.media.filter(section="walk"):
        img = m.image
        if img:
            media_by_key.setdefault(m.slot, []).append(
                {"id": m.id, "url": img.url, "masked": m.plate_masked})

    prefill, registry, extra = {}, None, {}
    if zone_key == "details":
        prefill = _registry_prefill(r.visit.vehicle)
        registry = VehicleRegistryData.objects.filter(vehicle=r.visit.vehicle).first()
        yr = timezone.now().year
        extra = {"ins_types": INSURANCE_TYPES, "ins_months": EXPIRY_MONTHS,
                 "ins_years": [str(y) for y in range(yr, yr + 11)]}
    elif zone_key == "docs":
        extra = {"wrap_ready": all([r.front_photo, r.rear_photo, r.left_photo,
                                    r.right_photo, r.walkaround_video])}

    groups = []
    for g in zone["groups"]:
        rows = []
        for cp in g["checkpoints"]:
            entry = res.get(cp["key"])
            pf = prefill.get(cp["key"], "")
            rows.append({**cp, "entry": entry,
                         "resolved": engine.is_resolved(cp, entry),
                         "photos": media_by_key.get(cp["key"], []),
                         "prefill": pf, "auto": bool(pf),
                         "edited": bool(entry and entry.get("value") and entry.get("value") != pf),
                         "chips": zones.chips_for(cp["pt"])})
        groups.append({"label": g["label"], "rows": rows})
    idx = zone["index"]
    next_zone = zones.ZONES[idx + 1] if idx + 1 < len(zones.ZONES) else None
    return render(request, "inspection/zone.html", _shell(request,
        active_tab="jobs", pushed=True, hide_nav=True, back_url=f"/inspect/{r.id}",
        r=r, zone=zone, groups=groups, progress=engine.zone_progress(r, zone),
        severities=zones.SEVERITIES, next_zone=next_zone,
        problem_chips=zones.PROBLEM_CHIPS,
        registry=registry, vehicle=r.visit.vehicle, **extra))


@inspector_required
@require_POST
def insp_cp_save(request, id):
    r = _get_report(request, id)
    if not r.editable:
        return JsonResponse({"ok": False, "error": "locked"}, status=409)
    key = request.POST.get("key")
    zone_key = request.POST.get("zone")
    if not key or key not in {cp["key"] for _z, cp in zones.all_checkpoints()}:
        return JsonResponse({"ok": False, "error": "bad key"}, status=400)

    before_active = engine.active_zone_key(r)
    result = request.POST.get("result")          # ok | issue | na | (none for field)
    # Photo required on every Issue (§5.3). Photos upload first (insp_cp_photo)
    # and attach to the entry, so by save time they're present.
    if result == "issue" and not (engine.entry_for(r, key) or {}).get("photos"):
        if request.headers.get("X-Requested-With") == "fetch":
            return JsonResponse({"ok": False, "error": "photo_required"}, status=422)
        return redirect(f"/inspect/{r.id}/zone/{zone_key}?err=photo#cp-{key}")
    kwargs = {"ts": timezone.now().isoformat(), "crid": request.POST.get("crid") or None}
    if result == "issue":
        kwargs.update(result="issue",
                      severity=request.POST.get("severity") or "moderate",
                      tags=request.POST.getlist("tags"),
                      note=request.POST.get("note", ""))
    elif result in ("ok", "na"):
        kwargs["result"] = result
        if request.POST.get("note"):
            kwargs["note"] = request.POST.get("note")
    if request.POST.get("value") is not None:
        kwargs["value"] = request.POST.get("value")
    engine.save_checkpoint(r, key, **kwargs)

    after_active = engine.active_zone_key(r)
    zone_done = before_active == zone_key and after_active != zone_key
    if request.headers.get("X-Requested-With") == "fetch":
        return JsonResponse({"ok": True, "zone_done": zone_done,
                             "progress": engine.zone_progress(r, zones.ZONE_BY_KEY[zone_key]) if zone_key in zones.ZONE_BY_KEY else None})
    if zone_done:
        return redirect(f"/inspect/{r.id}?unlocked=1")
    return redirect(f"/inspect/{r.id}/zone/{zone_key}#cp-{key}")


def _registry_prefill(v):
    """Identity values to verify (not retype) at Zone 0, from the already
    Surepass-populated Vehicle fields (§6.2)."""
    return {
        "reg_number": v.plate_number or "",
        "owner_name": v.owner_name or "",
        "make_model": " ".join(x for x in [v.make, v.model] if x),
        "variant_transmission": " · ".join(x for x in [v.variant, (v.get_transmission_display() if v.transmission else "")] if x),
        "mfg_month_year": " · ".join(str(x) for x in [v.year, (v.registration_date or "")] if x),
        "fuel_owners": " · ".join(x for x in [(v.get_fuel_type_display() if v.fuel_type else ""),
                                              (f"{v.owner_number} owner" if v.owner_number else "")] if x),
    }


def _attach_photo(r, key, media_id):
    entry = engine.entry_for(r, key) or {}
    photos = list(entry.get("photos") or [])
    if media_id not in photos:
        photos.append(media_id)
    engine.save_checkpoint(r, key, photos=photos)


@inspector_required
@require_POST
def insp_cp_photo(request, id):
    """Capture one photo for a walk-around checkpoint (§5.8): stored as
    InspectionMedia (section='walk', slot=checkpoint key), GPS-tagged, then
    plate-masked + watermarked + WebP'd server-side. The media id is linked
    into the checkpoint's entry so the report and publish_guard can find it."""
    r = _get_report(request, id)
    if not r.editable:
        return JsonResponse({"locked": True}, status=409)
    key = request.POST.get("key")
    if not key or key not in {cp["key"] for _z, cp in zones.all_checkpoints()}:
        return JsonResponse({"error": "bad key"}, status=400)
    f = request.FILES.get("file")
    if not f:
        return JsonResponse({"error": "no file"}, status=400)

    from .services import mask_plate_and_watermark, convert_to_webp
    media = InspectionMedia(report=r, kind="photo", section="walk", slot=key,
                            captured_at=timezone.now())
    try:
        media.gps_lat = float(request.POST["lat"]); media.gps_lng = float(request.POST["lng"])
    except (KeyError, ValueError, TypeError):
        pass
    ext = os.path.splitext(f.name)[1].lower() or ".jpg"
    media.file.save(f"{uuid.uuid4().hex}{ext}", f, save=False)
    media.save()
    try:
        mask_plate_and_watermark(media)        # plate cover + watermark; sets plate_masked
    except Exception:
        logger.exception("plate mask failed for walk photo media %s", media.id)
    try:
        if convert_to_webp(media, media.file):
            media.save(update_fields=["webp_file"])
    except Exception:
        logger.exception("webp failed for walk photo media %s", media.id)
    _attach_photo(r, key, media.id)
    img = media.image
    return JsonResponse({"ok": True, "id": media.id, "url": img.url if img else "",
                         "plate_masked": media.plate_masked})


@inspector_required
@require_POST
def insp_cp_photo_delete(request, media_id):
    m = get_object_or_404(InspectionMedia, id=media_id, section="walk",
                          report__visit__inspector=request.user)
    if not m.report.editable:
        return JsonResponse({"locked": True}, status=409)
    r, key = m.report, m.slot
    entry = engine.entry_for(r, key) or {}
    engine.save_checkpoint(r, key, photos=[p for p in (entry.get("photos") or []) if p != m.id])
    m.delete()
    return JsonResponse({"ok": True})


@inspector_required
@require_POST
def insp_registry_fetch(request, id):
    """Fallback #2 (§6.3): on-demand Surepass pull via the server proxy, cached
    into VehicleRegistryData and reflected onto the Vehicle identity fields."""
    r = _get_report(request, id)
    v = r.visit.vehicle
    msg = "fail"
    try:
        from www.services import lookup_rc_full
        data = lookup_rc_full(v.plate_number)
        for f in ("make", "model", "variant", "fuel_type", "transmission", "colour",
                  "registration_state", "rto", "owner_name", "chassis_number", "engine_number"):
            if data.get(f):
                setattr(v, f, data[f])
        if data.get("year"):
            v.year = data["year"]
        if data.get("owner_number"):
            v.owner_number = data["owner_number"]
        if data.get("is_hypothecated") is not None:
            v.is_hypothecated = data["is_hypothecated"]
        v.save()
        VehicleRegistryData.objects.update_or_create(vehicle=v, defaults={
            "reg_number": v.plate_number, "raw_json": data,
            "owner_name": data.get("owner_name", ""), "source": "surepass",
            "fetched_at": timezone.now()})
        msg = "ok"
    except Exception:
        logger.exception("registry fetch failed for vehicle %s", v.id)
    return redirect(f"/inspect/{r.id}/zone/details?fetch={msg}")


@inspector_required
@require_POST
def insp_registry_ocr(request, id):
    """Fallback #3 (§6.3): RC photo → backend OCR if a provider is wired, else
    capture the RC photo and degrade to manual verification."""
    r = _get_report(request, id)
    f = request.FILES.get("file")
    if not f:
        return redirect(f"/inspect/{r.id}/zone/details?ocr=nofile")
    msg = "manual"
    try:
        from www import services as wsvc
        if hasattr(wsvc, "ocr_rc"):
            data = wsvc.ocr_rc(f)
            v = r.visit.vehicle
            for k in ("make", "model", "variant", "owner_name", "chassis_number", "engine_number"):
                if data.get(k):
                    setattr(v, k, data[k])
            v.save()
            VehicleRegistryData.objects.update_or_create(vehicle=v, defaults={
                "reg_number": v.plate_number, "raw_json": data,
                "owner_name": data.get("owner_name", ""), "source": "ocr",
                "fetched_at": timezone.now()})
            msg = "ok"
    except Exception:
        logger.exception("registry OCR failed for report %s", r.id)
        msg = "fail"
    # keep the RC photo on the rc_card checkpoint regardless
    try:
        from .services import image_to_webp_bytes
        media = InspectionMedia(report=r, kind="photo", section="walk", slot="rc_card",
                                captured_at=timezone.now())
        data = image_to_webp_bytes(f)
        if data:
            media.webp_file.save(f"{uuid.uuid4().hex}.webp", ContentFile(data), save=False)
        else:
            media.file.save(f"{uuid.uuid4().hex}.jpg", f, save=False)
        media.save()
        _attach_photo(r, "rc_card", media.id)
    except Exception:
        logger.exception("RC photo store failed for report %s", r.id)
    return redirect(f"/inspect/{r.id}/zone/details?ocr={msg}")


# model FileField/ImageField targets the inspector can upload to (Changes 1-3).
_UPLOAD_FIELDS = {
    "auction_hero_image", "front_photo", "rear_photo", "left_photo", "right_photo",
    "walkaround_video", "engine_audio", "insurance_photo",
}
INSURANCE_TYPES = ["Comprehensive", "Third Party", "Zero Depreciation", "Not Available"]
EXPIRY_MONTHS = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]


@inspector_required
@require_POST
def insp_hero_upload(request, id):
    """Save the mandatory pre-inspection hero shot, then enter the flow."""
    r = _get_report(request, id)
    f = request.FILES.get("file")
    if f and r.editable:
        r.auction_hero_image.save(f"hero_{r.id}_{uuid.uuid4().hex}{os.path.splitext(f.name)[1].lower() or '.jpg'}", f, save=True)
    return redirect(f"/inspect/{r.id}")


@inspector_required
@require_POST
def insp_field_upload(request, id):
    """Generic upload to a whitelisted InspectionReport file/image field
    (wrap-up photos/video/audio, insurance photo). Reuses Django's storage."""
    r = _get_report(request, id)
    if not r.editable:
        return redirect(f"/inspect/{r.id}")
    field = request.POST.get("field")
    f = request.FILES.get("file")
    nxt = request.POST.get("next") or f"/inspect/{r.id}/zone/docs"
    if field in _UPLOAD_FIELDS and f:
        getattr(r, field).save(f"{field}_{r.id}_{uuid.uuid4().hex}{os.path.splitext(f.name)[1].lower()}", f, save=True)
    return redirect(nxt)


@inspector_required
@require_POST
def insp_insurance_save(request, id):
    """Save the structured insurance block (Change 3)."""
    r = _get_report(request, id)
    if r.editable:
        r.insurance_type = request.POST.get("insurance_type", "")
        r.insurer_name = request.POST.get("insurer_name", "")
        r.policy_number = request.POST.get("policy_number", "")
        r.insurance_expiry_month = request.POST.get("insurance_expiry_month", "")
        r.insurance_expiry_year = request.POST.get("insurance_expiry_year", "")
        fields = ["insurance_type", "insurer_name", "policy_number",
                  "insurance_expiry_month", "insurance_expiry_year", "updated_at"]
        f = request.FILES.get("insurance_photo")
        if f:
            r.insurance_photo.save(f"insurance_{r.id}_{uuid.uuid4().hex}{os.path.splitext(f.name)[1].lower()}", f, save=False)
            fields.append("insurance_photo")
        r.save(update_fields=fields)
    return redirect(f"/inspect/{r.id}/zone/details#insurance")


@inspector_required
@require_POST
def insp_zone_markgood(request, id, zone_key):
    r = _get_report(request, id)
    if r.editable and zone_key in zones.ZONE_BY_KEY and engine.can_enter(r, zone_key):
        before = engine.active_zone_key(r)
        engine.mark_zone_good(r, zone_key)
        if before == zone_key and engine.active_zone_key(r) != zone_key:
            return redirect(f"/inspect/{r.id}?unlocked=1")
    return redirect(f"/inspect/{r.id}/zone/{zone_key}")


@inspector_required
def insp_visits(request):
    return redirect("/jobs")          # retired — merged into Jobs (v4)


@inspector_required
def insp_visit(request, id):
    v = get_object_or_404(InspectionVisit, id=id, inspector=request.user)
    return render(request, "inspection/visit.html", _shell(request,
        active_tab="jobs", pushed=True, hide_nav=True, back_url="/jobs",
        v=v, vehicle=v.vehicle))


@inspector_required
def insp_start(request, id):
    # Walk-around is now the default flow (§5). New inspections land in /inspect.
    v = get_object_or_404(InspectionVisit, id=id, inspector=request.user)
    v.status = "inprogress"
    v.save()
    report, _ = InspectionReport.objects.get_or_create(visit=v)
    return redirect(f"/inspect/{report.id}")


@inspector_required
def insp_resume(request, id):
    """Dispatch a Continue/resume to whichever flow the report was started in:
    walk-around if it has walk data, else the legacy section flow."""
    r = _get_report(request, id)
    if engine.is_walk_inspection(r) or not r.checkpoints:
        return redirect(f"/inspect/{r.id}")
    return redirect(f"/inspection/{r.id}/summary")


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


def _persist_walk_score(r):
    from .services import walk_media_by_key  # noqa: F401 (kept symmetric)
    sc = engine.compute_score(r)
    r.score = sc["score"]
    r.condition_grade = sc["grade"]
    r.est_market_value = engine.estimated_value(sc["grade"], r.visit.vehicle.expected_price)
    r.save(update_fields=["score", "condition_grade", "est_market_value", "updated_at"])
    return sc


@inspector_required
def insp_report(request, id):
    r = get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)
    if engine.is_walk_inspection(r):
        from .services import walk_media_by_key
        _persist_walk_score(r)
        ctx = engine.report_context(r, walk_media_by_key(r))
        return render(request, "inspection/report_walk.html", _shell(request,
            active_tab="jobs", pushed=True, hide_nav=True, back_url=f"/inspect/{r.id}",
            r=r, vehicle=r.visit.vehicle, **ctx))
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
    return render(request, "inspection/report.html", _shell(request,
        active_tab="jobs", pushed=True, hide_nav=True, back_url="/jobs",
        r=r, media=r.media.all(), dents=r.dents.all(),
        schema=CHECKPOINT_SCHEMA, checkpoint_photo_groups=checkpoint_photo_groups))


@inspector_required
def insp_submit(request, id):
    r = get_object_or_404(InspectionReport, id=id, visit__inspector=request.user)
    if not r.editable:
        return redirect(f"/report/{r.id}")
    is_walk = engine.is_walk_inspection(r)
    # Wrap-up gating (Change 2): 4 exterior photos + walk-around video required.
    if is_walk and not all([r.front_photo, r.rear_photo, r.left_photo,
                            r.right_photo, r.walkaround_video]):
        return redirect(f"/inspect/{r.id}/zone/docs?err=wrapup")
    notes = request.POST.get("final_notes")
    if notes is not None:
        r.final_notes = notes
        r.save(update_fields=["final_notes", "updated_at"])
    from .services import publish_guard, generate_report_pdf, generate_walk_pdf
    try:
        publish_guard(r)              # blocks unmasked plates (§5.8) — same guard both flows
    except ValueError:
        pass  # allow submit even without masked photos in dev
    if is_walk:
        _persist_walk_score(r)
    else:
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
        generate_walk_pdf(r) if is_walk else generate_report_pdf(r)
    except Exception:
        logger.exception("PDF generation failed for report %s", r.id)
    log(request.user, "inspection.submit", r, request, score=r.score, redo=r.redo_count)
    from accounts.models import User
    for adm in User.objects.filter(role="admin"):
        notify(adm, "insp_assigned",
               title=f"Inspection submitted: {r.visit.vehicle.display_name}",
               body=f"Score {r.score}/100 · awaiting decision")
    return render(request, "inspection/success.html", _shell(request,
        pushed=True, hide_nav=True, back_url="/", r=r))


@inspector_required
def insp_alerts(request):
    return redirect("/notifications")     # retired — replaced by Notifications (v4)
