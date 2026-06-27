import datetime
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.decorators import admin_required
from core.models import log
from notifications.services import notify
from .models import InspectionReport
from .schema import CHECKPOINT_SCHEMA


@admin_required
def inspection_queue(request):
    reports = (
        InspectionReport.objects
        .filter(visit__status="submitted")
        .select_related("visit__vehicle", "visit__inspector")
    )
    return render(request, "master/inspection_queue.html", {
        "active": "inspections",
        "reports": reports,
    })


@admin_required
def inspection_review(request, id):
    r = get_object_or_404(InspectionReport, id=id)
    from . import engine
    is_walk = engine.is_walk_inspection(r)

    # Regenerate the PDF on demand (e.g. for reports submitted before a template
    # change). Only deletes the old file once weasyprint is confirmed available.
    if request.GET.get("refresh"):
        from .services import generate_report_pdf, generate_walk_pdf
        try:
            import weasyprint  # noqa: F401
            if r.pdf:
                r.pdf.delete(save=False)
            generate_walk_pdf(r) if is_walk else generate_report_pdf(r)
        except Exception:
            pass
        return redirect(f"/inspection_review/{id}")

    if is_walk:
        from .services import walk_media_by_key
        ctx = engine.report_context(r, walk_media_by_key(r))
        return render(request, "master/inspection_review_walk.html", {
            "active": "inspections", "r": r, "v": r.visit.vehicle, **ctx,
        })

    # Per-checkpoint photos grouped by (section, part key)
    cp_by = {}
    for ph in r.checkpoint_photos.all():
        cp_by.setdefault((ph.section, ph.checkpoint_key), []).append({"url": ph.image.url})

    # Pre-process checkpoints into template-friendly structure
    sections_data = []
    for sec_key, sec_schema in CHECKPOINT_SCHEMA.items():
        if sec_schema.get("kind") == "media":
            continue
        saved = r.checkpoints.get(sec_key, {})
        sec_row = {
            "key": sec_key,
            "label": sec_schema["label"],
            "is_summary": sec_key == "summary",
            "fields": [],
            "parts": [],
            "ok_count": 0,
            "issue_count": 0,
        }
        if sec_key == "summary":
            for field in sec_schema.get("fields", []):
                sec_row["fields"].append({"key": field, "value": saved.get(field, "—")})
        else:
            for part in sec_schema.get("parts", []):
                part_saved = saved.get(part["key"], {})
                subparts_data = []
                if part.get("subparts"):
                    for sub in part["subparts"]:
                        cell = part_saved.get(sub, {}) if isinstance(part_saved, dict) else {}
                        st = cell.get("status", "") if isinstance(cell, dict) else ""
                        if st == "ok":    sec_row["ok_count"] += 1
                        elif st == "issue": sec_row["issue_count"] += 1
                        subparts_data.append({
                            "label": sub, "status": st,
                            "condition": cell.get("condition", "") if isinstance(cell, dict) else "",
                            "value": cell.get("value", "") if isinstance(cell, dict) else "",
                        })
                else:
                    cell = part_saved.get("_", {}) if isinstance(part_saved, dict) else {}
                    st = cell.get("status", "") if isinstance(cell, dict) else ""
                    if st == "ok":    sec_row["ok_count"] += 1
                    elif st == "issue": sec_row["issue_count"] += 1
                    subparts_data.append({
                        "label": "", "status": st,
                        "condition": cell.get("condition", "") if isinstance(cell, dict) else "",
                        "value": cell.get("value", "") if isinstance(cell, dict) else "",
                    })
                sec_row["parts"].append({
                    "key": part["key"],
                    "label": part["label"],
                    "kind": part["kind"],
                    "unit": part.get("unit", ""),
                    "has_subparts": bool(part.get("subparts")),
                    "subparts": subparts_data,
                    "photos": cp_by.get((sec_key, part["key"]), []),
                })
        sections_data.append(sec_row)

    # Media: photo gallery + video + audio
    photos, videos, audios = [], [], []
    for m in r.media.all():
        if m.kind == "photo":
            img = m.webp_file or m.masked_file or m.file
            if img:
                photos.append({"slot": m.slot or m.section or "Photo", "url": img.url})
        elif m.kind == "video":
            vid = m.mp4_file or m.file
            if vid:
                videos.append({"url": vid.url})
        elif m.kind == "audio":
            if m.file:
                audios.append({"url": m.file.url})

    return render(request, "master/inspection_review.html", {
        "active": "inspections",
        "r": r,
        "v": r.visit.vehicle,
        "sections_data": sections_data,
        "photos": photos,
        "videos": videos,
        "audios": audios,
        "dents": r.dents.all(),
        "schema": CHECKPOINT_SCHEMA,
    })


@admin_required
@transaction.atomic
def inspection_decide(request, id):
    # Atomic: if ANY step fails (e.g. building a notification), the whole
    # decision rolls back — no orphaned auction / half-applied status changes.
    if request.method != "POST":
        return redirect(f"/inspection_review/{id}")
    r = get_object_or_404(InspectionReport, id=id)
    action = request.POST.get("action")
    r.decided_by = request.user
    r.decision_note = request.POST.get("note", "")

    if action == "approve":
        duration = int(request.POST.get("duration_minutes", 30))
        r.decision = "approved"
        r.save()
        v = r.visit
        v.status = "approved"
        v.vehicle.status = "listed"
        v.vehicle.save()
        v.save()
        from auctions.models import Auction
        start = timezone.now()
        a = Auction.objects.create(
            vehicle=v.vehicle,
            reserve_price=v.vehicle.expected_price,
            created_by=request.user,
            start_at=start,
            end_at=start + datetime.timedelta(minutes=duration),
            status="live",
        )
        # Pipeline: the InspectionVisit post_save signal advances the lead to
        # Admin Approved (it rests there for the Retail Head inbox — allocation
        # comes next; the auction entity created here does not auto-advance it).
        log(request.user, "inspection.approve", r, request, duration=duration, auction=a.id)
        notify(v.inspector, "insp_decision",
               title=f"Approved: {v.vehicle.display_name}",
               body=f"Auction is live for {duration} min.")
        notify(v.vehicle.seller, "auction_start",
               title=f"Auction live: {v.vehicle.display_name}",
               body=f"Live for {duration} minutes.")
        return redirect(f"/auction/{a.id}")

    if action == "redo":
        r.decision = "redo"
        r.is_locked = False
        r.redo_count += 1
        r.save()
        v = r.visit
        v.status = "reinspect"
        v.save()
        log(request.user, "inspection.redo", r, request, note=r.decision_note)
        notify(v.inspector, "insp_decision",
               title=f"Redo requested: {v.vehicle.display_name}",
               body=r.decision_note or "Please revise and resubmit your report.")
        return redirect("/inspection_queue")

    if action == "remove":
        r.decision = "removed"
        r.is_locked = True
        r.save()
        v = r.visit
        v.status = "rejected"
        v.save()
        log(request.user, "inspection.remove", r, request)
        notify(v.inspector, "insp_decision",
               title=f"Report removed: {v.vehicle.display_name}",
               body=r.decision_note or "This report was removed.")
        return redirect("/inspection_queue")

    return redirect(f"/inspection_review/{id}")
