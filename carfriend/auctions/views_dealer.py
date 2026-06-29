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
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.models import dealer_can_bid
from inspections.models import InspectionReport
from inspections.services import build_report_data
from inspections.templatetags.cf import short_car_name
from .models import Auction

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
    """Masked condition photos grouped by their section tag (dealer-safe)."""
    out = {}
    for m in report.media.filter(kind="photo").order_by("id"):
        img = m.masked_file or m.webp_file or m.file
        if img:
            out.setdefault((m.section or "").strip().lower(), []).append(img.url)
    return out


def dealer_inspection(report):
    """Redacted, render-ready inspection for the dealer room: per-zone accordion
    sections (condition only), masked photos, grade/score, challan flag and engine
    audio. NEVER seller PII, registry identity values, or the unmasked walk video."""
    if not report:
        return None
    from inspections import engine

    photos_by_sec = _media_by_section(report)
    sections = []

    if engine.is_walk_inspection(report):
        ctx = engine.report_context(report)          # pure read; no save
        grade = ctx.get("grade") or report.condition_grade
        score = ctx.get("score") or report.score
        for z in ctx.get("zones", []):
            zkey = z.get("key", "")
            identity_zone = zkey in ("details", "docs")
            items, ok, issue = [], 0, 0
            for g in z.get("groups", []):
                for r in g.get("rows", []):
                    label = r.get("label", "")
                    note = r.get("note") or r.get("value") or ""
                    st = r.get("result") or ""
                    if identity_zone and any(h in (label + " " + note).lower() for h in _REDACT_HINTS):
                        continue                     # hide registry identity rows
                    if not st and not note:
                        continue
                    if st == "ok": ok += 1
                    elif st == "issue": issue += 1
                    items.append({"label": label, "val": st, "sev": _sev_rank(r.get("severity")),
                                  "note": note, "is_ok": st == "ok", "is_issue": st == "issue"})
            if items:
                sections.append({"key": zkey, "label": z.get("title", ""),
                                 "icon": _ZONE_ICONS.get(zkey, "fa-circle-check"),
                                 "items": items, "item_count": len(items),
                                 "ok_count": ok, "issue_count": issue,
                                 "photos": photos_by_sec.get(zkey, [])})
    else:
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

    return {
        "grade": grade,
        "score": score,
        "sections": sections,
        "hero": _hero_url(report),
        "has_challans": (report.challan_count or 0) > 0,
        "audio_url": report.engine_audio.url if report.engine_audio else None,
        # walkaround_video intentionally omitted — it is NOT plate-masked.
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
    bids = [{"amount": b.amount, "ts": b.created_at, "is_me": b.dealer_id == request.user.id}
            for b in a.bids.filter(is_voided=False).order_by("-created_at")[:50]]
    return render(request, "auctions/dealer_room.html", {
        "a":           dealer_auction(a),
        "auction_id":  a.id,
        "can_bid":     dealer_can_bid(request.user),
        "my_id":       request.user.id,
        "inspection":  dealer_inspection(report),
        "bids":        bids,
    })
