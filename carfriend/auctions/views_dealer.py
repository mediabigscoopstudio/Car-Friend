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


def dealer_inspection(report):
    """Redacted inspection data: condition only — never seller/PII."""
    if not report:
        return None
    sections = build_report_data(report).get("sections", [])   # statuses + notes (+ checkpoint photos)
    photos = _photo_urls(report)
    return {
        "grade": report.condition_grade,
        "sections": sections,
        "photos": photos,
        "hero": photos[0] if photos else None,   # primary/cover image
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
        photos = _photo_urls(_vehicle_report(a.vehicle))
        card["cover"] = photos[0] if photos else None
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
