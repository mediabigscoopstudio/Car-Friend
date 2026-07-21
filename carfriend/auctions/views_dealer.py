"""Dealer-facing auction pages (public/www host).

Single source of dealer-safe serialization: NOTHING sensitive about the seller
or the raw vehicle identity leaves these helpers. Excluded everywhere:
seller name/phone/email/address, expected/asking price, plate/registration,
chassis/engine number, owner name/number, internal score, inspector identity,
decision notes. Included: spec (make/model/year/fuel/transmission/km/city),
condition grade + checkpoint statuses/notes, condition photos (plate-masked
preferred), and the challan block.
"""
import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.models import dealer_can_bid
from inspections.models import InspectionReport
from inspections.services import build_report_data
from inspections.templatetags.cf import short_car_name
from . import services
from .models import Auction, AutoBid

logger = logging.getLogger(__name__)


def _bounce_non_dealer(request):
    """Dealers only (any authenticated dealer may VIEW). Non-dealers → home."""
    if not request.user.is_dealer:
        return redirect("/")
    return None


def _live_auctions():
    now = timezone.now()
    return (Auction.objects.filter(status="live", start_at__lte=now, end_at__gt=now)
            .select_related("vehicle").order_by("end_at"))


# ── dealer-safe serialization (single source) ───────────────────────────────

def dealer_vehicle(v):
    return {
        "name":         short_car_name(v),                                   # make/model/variant only
        "year":         v.year,
        "fuel":         v.get_fuel_type_display() if v.fuel_type else "",
        "transmission": v.get_transmission_display() if v.transmission else "",
        "km":           v.odometer_km,
        "city":         v.city,
        "grade":        v.condition_grade,
    }


def dealer_auction(a):
    hb = a.highest_bid
    return {
        "id":            a.id,
        "vehicle":       dealer_vehicle(a.vehicle),
        "highest":       hb.amount if hb else None,
        "reserve":       a.reserve_price,
        "min_increment": a.min_increment,
        "end_ts":        int(a.end_at.timestamp()),
    }


def _vehicle_report(vehicle):
    return (InspectionReport.objects
            .filter(visit__vehicle=vehicle)
            .order_by("-submitted_at").first())


def _photo_urls(report):
    """Dealer-safe photo URLs (masked/plate-hidden preferred), in upload order."""
    urls = []
    if report:
        for m in report.media.filter(kind="photo").order_by("id"):
            img = m.masked_file or m.webp_file or m.file
            if img:
                urls.append(img.url)
    return urls


def _hero_url(report):
    """Dealer cover image: the pre-inspection HERO shot (3/4 front, plate-masked),
    then a wrap-up front photo, then the first masked condition photo. NEVER a
    document/insurance image."""
    if not report:
        return None
    if report.auction_hero_image:
        return report.auction_hero_image.url        # masked on upload (_MASK_PHOTO_FIELDS)
    if report.front_photo:
        return report.front_photo.url               # masked on upload
    photos = _photo_urls(report)                    # masked condition photos
    return photos[0] if photos else None


# Font-Awesome icon per walk-around zone (zones.py keys).
_ZONE_ICONS = {"details": "fa-id-card", "left": "fa-car-side", "front": "fa-gear",
               "right": "fa-car-side", "rear": "fa-car-rear", "inside": "fa-couch",
               "docs": "fa-file-lines"}
# Identity hints redacted from the registry/docs zones (never shown to dealers).
_REDACT_HINTS = ("chassis", "registration", "reg no", "reg number", "plate",
                 "number plate", "owner", "vin", "engine number", "engine no")


def _sev_rank(severity):
    if severity in ("major", "critical", "severe"):
        return 2
    return 1 if severity == "minor" else 0


def _media_by_section(report):
    """Masked condition photos grouped by the ZONE they belong to (dealer-safe).

    Walk-inspection photos are stored as InspectionMedia(section='walk', slot=<checkpoint
    key>), so grouping by `section` dumps them all in a 'walk' bucket that no dealer zone
    ever looks up. Map each checkpoint key back to its zone key; legacy media (which carry
    a real section) fall back to that section. All three file variants are plate-masked
    (the raw file is masked in place on upload), so any is dealer-safe."""
    from inspections import zones
    key_to_zone = {cp["key"]: zkey for zkey, cp in zones.all_checkpoints()}
    out = {}
    for m in report.media.filter(kind="photo").order_by("id"):
        img = m.masked_file or m.webp_file or m.file
        if not img:
            continue
        zkey = key_to_zone.get(m.slot) or (m.section or "").strip().lower()
        out.setdefault(zkey, []).append(img.url)
    return out


def _media_by_checkpoint(report):
    """Dealer-safe (masked) photos keyed by the CHECKPOINT they document.

    Walk photos are saved as InspectionMedia(section='walk', slot=<checkpoint key>), so
    `slot` is the checkpoint key — the same key report_context uses per row. Returns
    ({checkpoint_key: [url,...]}, [loose urls with no checkpoint]). All variants are
    plate-masked (raw file masked in place on upload), so any is dealer-safe."""
    out, loose = {}, []
    for m in report.media.filter(kind="photo").order_by("id"):
        img = m.masked_file or m.webp_file or m.file
        if not img:
            continue
        if m.slot:
            out.setdefault(m.slot, []).append(img.url)
        else:
            loose.append(img.url)
    return out, loose


def dealer_inspection(report):
    """Redacted, render-ready inspection for the dealer room: per-zone accordion
    sections (condition only), masked photos, grade/score, challan flag and engine
    audio. NEVER seller PII, registry identity values, or the unmasked walk video."""
    if not report:
        return None
    from inspections import engine

    sections = []
    other_photos = []

    if engine.is_walk_inspection(report):
        # Feed the per-checkpoint photo map into report_context so each ROW carries its
        # OWN photos (row["photos"] = media_by_key[cp_key]) — rendered with the checkpoint
        # instead of pooled at the section bottom.
        media_by_cp, loose = _media_by_checkpoint(report)
        ctx = engine.report_context(report, media_by_cp)   # pure read; no save
        grade = ctx.get("grade") or report.condition_grade
        score = ctx.get("score") or report.score
        shown, redacted = set(), set()
        for z in ctx.get("zones", []):
            zkey = z.get("key", "")
            identity_zone = zkey in ("details", "docs")
            items, ok, issue = [], 0, 0
            for g in z.get("groups", []):
                for r in g.get("rows", []):
                    label = r.get("label", "")
                    note = r.get("note") or r.get("value") or ""
                    st = r.get("result") or ""
                    rphotos = r.get("photos") or []
                    if identity_zone and any(h in (label + " " + note).lower() for h in _REDACT_HINTS):
                        redacted.update(rphotos)     # identity row → drop its photo too
                        continue                     # hide registry identity rows
                    if not st and not note and not rphotos:
                        continue                     # a photographed checkpoint still shows
                    if st == "ok": ok += 1
                    elif st == "issue": issue += 1
                    shown.update(rphotos)
                    items.append({"label": label, "val": st, "sev": _sev_rank(r.get("severity")),
                                  "note": note, "is_ok": st == "ok", "is_issue": st == "issue",
                                  "photos": rphotos})
            if items:
                sections.append({"key": zkey, "label": z.get("title", ""),
                                 "icon": _ZONE_ICONS.get(zkey, "fa-circle-check"),
                                 "items": items, "item_count": len(items),
                                 "ok_count": ok, "issue_count": issue})
        # Any masked photo not shown on a row and not identity-redacted is genuinely
        # section-level (e.g. a checkpoint that never rendered, or a slot-less photo) —
        # keep those in one "Other inspection photos" strip so nothing is lost. With full
        # checkpoint linkage this is empty and the strip disappears.
        all_urls = [u for urls in media_by_cp.values() for u in urls] + loose
        other_photos = [u for u in all_urls if u not in shown and u not in redacted]
    else:
        photos_by_sec = _media_by_section(report)    # legacy form: section-level photos
        grade, score = report.condition_grade, report.score
        for s in build_report_data(report).get("sections", []):
            if not s.get("filled"):
                continue
            items, ok, issue = [], 0, 0
            for part in s["filled"]:
                for row in part.get("rows", []):
                    st = row.get("status") or ""
                    note = row.get("condition") or row.get("value") or ""
                    if not st and not note:
                        continue
                    if st == "ok": ok += 1
                    elif st == "issue": issue += 1
                    plabel = part.get("label", "")
                    if row.get("label"):
                        plabel = f"{plabel} · {row['label']}"
                    items.append({"label": plabel, "val": st, "sev": 2 if st == "issue" else 0,
                                  "note": note, "is_ok": st == "ok", "is_issue": st == "issue"})
            if items:
                key = s.get("key", "sec")
                sections.append({"key": key, "label": s.get("label", ""),
                                 "icon": _ZONE_ICONS.get(key, "fa-circle-check"),
                                 "items": items, "item_count": len(items),
                                 "ok_count": ok, "issue_count": issue,
                                 "photos": photos_by_sec.get(key, [])})

    # Test-drive summary — distance + duration + drivability ONLY. The GPS route
    # map is admin-only (it would reveal the seller's location), so never sent here.
    drive = None
    if report.is_drivable is not None:
        drive = {
            "is_drivable": report.is_drivable,
            "towing_needed": report.towing_needed,
            "distance_km": report.distance_km,
            "duration_min": round(report.duration_seconds / 60) if report.duration_seconds else None,
            "suspension": report.get_suspension_condition_display() if report.suspension_condition else None,
            "brake": report.get_brake_condition_display() if report.brake_condition else None,
        }

    # Wrap-up 4-side photos live on the report itself (front/rear/left/right), and are
    # plate-masked on upload (_MASK_PHOTO_FIELDS) — dealer-safe.
    wrap_photos = [f.url for f in (report.front_photo, report.rear_photo,
                                   report.left_photo, report.right_photo) if f]
    return {
        "grade": grade,
        "score": score,
        "sections": sections,
        "other_photos": other_photos,   # masked photos not tied to a shown checkpoint
        "hero": _hero_url(report),
        "has_challans": (report.challan_count or 0) > 0,
        "audio_url": report.engine_audio.url if report.engine_audio else None,
        "video_url": report.walkaround_video.url if report.walkaround_video else None,
        "wrap_photos": wrap_photos,
        "drive": drive,          # distance/duration/drivability only — NO route map
        "report": report,
    }


# ── views ────────────────────────────────────────────────────────────────────

@login_required(login_url="/auth/login/")
def dealer_auction_list(request):
    guard = _bounce_non_dealer(request)
    if guard:
        return guard
    cards = []
    for a in _live_auctions():
        card = dealer_auction(a)
        card["cover"] = _hero_url(_vehicle_report(a.vehicle))   # hero shot, not insurance/doc
        cards.append(card)
    return render(request, "auctions/dealer_list.html", {
        "auctions": cards,
        "can_bid":  dealer_can_bid(request.user),
    })


@login_required(login_url="/auth/login/")
def dealer_purchases(request):
    """Dealer's won/closed deals with payment status. Reuses deals.Deal +
    payments.Payment; no new model."""
    guard = _bounce_non_dealer(request)
    if guard:
        return guard
    from deals.models import Deal
    from payments.models import Payment
    # Include "agreement" so the dealer can reach + e-sign the agreement BEFORE it is
    # fully signed (the deal only becomes "signed" once both parties have signed).
    deals = (Deal.objects.filter(dealer=request.user,
                                 status__in=["agreement", "signed", "paid", "closed"])
             .select_related("vehicle", "agreement").order_by("-created_at"))
    rows = []
    for d in deals:
        p = Payment.objects.filter(deal=d).order_by("-id").first()
        ag = getattr(d, "agreement", None)
        rows.append({"deal": d, "paid": bool(p and p.status == "confirmed"),
                     "dealer_signed": bool(ag and ag.dealer_signed),
                     "needs_sign": bool(ag and not ag.dealer_signed)})
    return render(request, "auctions/dealer_purchases.html", {"rows": rows})


@login_required(login_url="/auth/login/")
def dealer_auction_room(request, id):
    guard = _bounce_non_dealer(request)
    if guard:
        return guard
    a = get_object_or_404(Auction.objects.select_related("vehicle"), id=id)
    if not a.is_live:
        return redirect("/auctions/")
    report = (InspectionReport.objects
              .filter(visit__vehicle=a.vehicle)
              .order_by("-submitted_at").first())
    # Live feed = CURRENT-round bids only (created after this round's start).
    bids = [{"amount": b.amount, "ts": b.created_at, "is_me": b.dealer_id == request.user.id}
            for b in a.bids.filter(is_voided=False, created_at__gte=a.start_at)
                            .order_by("-created_at")[:50]]
    # This dealer's own bid from a PRIOR round — context only ("Your last bid").
    my_prev = None
    if a.reactivation_count:
        my_prev = (a.bids.filter(dealer=request.user, created_at__lt=a.start_at)
                   .order_by("-amount").first())
    # Dealer's own active auto-bid ceiling, if any — read back so the toggle/ceiling
    # UI and the auto-bid status row survive a page refresh (auctions/models.AutoBid).
    ab = AutoBid.objects.filter(auction=a, dealer=request.user, is_active=True).first()
    auto_bid = {"max_amount": ab.max_amount} if ab else None
    return render(request, "auctions/dealer_room.html", {
        "a":            dealer_auction(a),
        "auction_id":   a.id,
        "can_bid":      dealer_can_bid(request.user),
        "my_id":        request.user.id,
        "inspection":   dealer_inspection(report),
        "bids":         bids,
        "my_prev_bid":  my_prev.amount if my_prev else None,
        "auto_bid":     auto_bid,
    })


# ── auto-bid (proxy bidding) ────────────────────────────────────────────────

@login_required(login_url="/auth/login/")
def dealer_auto_bid_set(request, id):
    """Set/update/re-activate the dealer's auto-bid ceiling for this auction. Engages
    immediately (via services.run_auto_bids) if the ceiling already clears the current
    floor, same as standard proxy-bidding UX — not reactive-only."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required."}, status=405)
    guard = _bounce_non_dealer(request)
    if guard:
        return guard
    if not dealer_can_bid(request.user):
        return JsonResponse({"ok": False, "error": "Complete dealer verification to use auto-bid."}, status=403)
    try:
        max_amount = int(request.POST.get("max_amount", ""))
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "Enter a valid ceiling amount."}, status=400)
    if max_amount <= 0:
        return JsonResponse({"ok": False, "error": "Enter a valid ceiling amount."}, status=400)

    with transaction.atomic():
        a = get_object_or_404(Auction.objects.select_for_update(), id=id)
        if not a.is_live:
            return JsonResponse({"ok": False, "error": "Auction is not live."}, status=400)
        hb = a.highest_bid
        current = hb.amount if hb else a.reserve_price
        # Per spec: the ceiling must beat the CURRENT highest bid (not the next floor).
        # A ceiling only 1 rupee above `current` is accepted here but stays functionally
        # inert until raised, since current_floor is always current + min_increment.
        if max_amount <= current:
            return JsonResponse({
                "ok": False,
                "error": f"Ceiling must be higher than the current highest bid (₹{current:,}).",
            }, status=400)
        auto_bid, _ = AutoBid.objects.update_or_create(
            auction=a, dealer=request.user,
            defaults={"max_amount": max_amount, "is_active": True},
        )
        new_bids = services.run_auto_bids(a)
        transaction.on_commit(lambda: services.broadcast_bids(a.id, new_bids))

    return JsonResponse({"ok": True, "max_amount": auto_bid.max_amount, "is_active": True})


@login_required(login_url="/auth/login/")
def dealer_auto_bid_cancel(request, id):
    """Deactivate the dealer's auto-bid for this auction. Never re-runs the cascade —
    cancelling never creates a new obligation for anyone else, the floor doesn't change."""
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required."}, status=405)
    guard = _bounce_non_dealer(request)
    if guard:
        return guard
    with transaction.atomic():
        a = get_object_or_404(Auction.objects.select_for_update(), id=id)
        AutoBid.objects.filter(auction=a, dealer=request.user).update(is_active=False)
    return JsonResponse({"ok": True})


def live_room_context(a, back_url):
    """Context for the FULL read-only live room shown to master + Retail Head:
    car info, the (reused) dealer inspection viewer, a real-time named bid feed
    with REAL dealer names, and BOTH money sides (dealer GROSS + seller BASE
    de-grossed via core.margin). Read-only — no bidding. Callers guard access."""
    import json
    from core.margin import base_from_gross, inverse_params
    v = a.vehicle
    hb = a.highest_bid
    gross = hb.amount if hb else a.reserve_price
    report = _vehicle_report(v)
    bids, names = [], {}
    for b in (a.bids.filter(is_voided=False).select_related("dealer")
              .order_by("-created_at")[:60]):
        nm = (b.dealer.get_full_name() or b.dealer.username) if b.dealer else "Dealer"
        bids.append({"name": nm, "amount": b.amount, "ts": b.created_at})
        if b.dealer_id:
            names[b.dealer_id] = nm
    p = inverse_params()
    return {
        "a": a, "v": v, "back_url": back_url,
        "gross_fmt": f"{gross:,}", "base_fmt": f"{base_from_gross(gross)['base']:,}",
        "reserve_gross_fmt": f"{a.reserve_price:,}",
        "reserve_base_fmt": f"{base_from_gross(a.reserve_price)['base']:,}",
        "bidders": a.bids.filter(is_voided=False).values("dealer").distinct().count(),
        "bid_count": a.bids.filter(is_voided=False).count(),
        "inspection": dealer_inspection(report),
        "report_url": report.pdf.url if report and report.pdf else None,
        "hero_url": (report.auction_hero_image.url
                     if report and report.auction_hero_image else None),
        "bids": bids, "names_json": json.dumps(names),
        "cf_k": p["k"], "cf_boundary": p["boundary"], "cf_floor_gst": p["floor_gst"],
    }
