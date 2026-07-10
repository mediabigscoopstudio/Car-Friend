"""Mobile-app (/app/*) pages for the Android WebView apps.

Purely additive — a NEW surface that coexists with the marketing homepage (/), the
existing /auth/* auth, and the seller/dealer dashboards. Nothing here modifies those.

The GROSS/BASE wall (spec §1) is enforced in every view:
  - Dealer surfaces show GROSS (reserve_price, Bid.amount straight from the DB).
  - Seller surfaces show BASE — every dealer number is de-grossed via core.margin.base_from_gross.
"""

import re
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import Role, User
from accounts.views import get_dashboard_url
from auctions.models import Auction
from auctions.ocb_services import open_round_listings
from core.margin import base_from_gross
from vehicles.models import Vehicle

STATS_MIN = 10  # hide the welcome stats row unless we have a non-embarrassing real number


def _live_auction_qs():
    return Auction.objects.filter(status=Auction.Status.LIVE)


def _inr(n):
    """Indian-grouped rupee string (e.g. 541300 -> '5,41,300'). No humanize dependency."""
    if n is None:
        return None
    n = int(n)
    s = str(abs(n))
    if len(s) <= 3:
        grouped = s
    else:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(?<=\d)(?=(\d\d)+$)", ",", head)
        grouped = head + "," + tail
    return ("-" if n < 0 else "") + grouped


# ── 1 + 5. Role-aware router / pre-login welcome ────────────────────────────────
def app_router(request):
    """GET /app/ — the single entry point the Android apps point at.

    Not logged in  -> the welcome page.
    Seller / dealer -> their app home. Staff -> their existing dashboard.
    """
    u = request.user
    if u.is_authenticated:
        if u.is_seller:
            return redirect("/app/seller/")
        if u.is_dealer:
            return redirect("/app/dealer/")
        return redirect(get_dashboard_url(u))

    cars_sold = Vehicle.objects.filter(status=Vehicle.STATUS_SOLD).count()
    dealers = User.objects.filter(role=Role.DEALER).count()
    return render(request, "www/app/welcome.html", {
        "live_count": _live_auction_qs().count(),
        "cars_sold": cars_sold,
        "dealers": dealers,
        # Only real numbers, and only when they are not embarrassingly small.
        "show_stats": cars_sold >= STATS_MIN,
    })


# ── 2. Phone-OTP login / register ──────────────────────────────────────────────
def app_login(request):
    """GET /app/login/ — existing users; no role sent on verify (role never changes)."""
    if request.user.is_authenticated:
        return redirect("/app/")
    return render(request, "www/app/login.html", {"otp_role": ""})


def app_register(request):
    """GET /app/register/ — new signups. role=seller by default; ?role=dealer for the dealer app."""
    if request.user.is_authenticated:
        return redirect("/app/")
    role = "dealer" if request.GET.get("role") == "dealer" else "seller"
    return render(request, "www/app/register.html", {"otp_role": role})


# ── 3. Seller home ─────────────────────────────────────────────────────────────
def _seller_status_label(vehicle, live_auction):
    if live_auction is not None:
        return "Auction live"
    if vehicle.status == Vehicle.STATUS_SOLD:
        return "Sold"
    if vehicle.status == Vehicle.STATUS_INSPECTION:
        return "Inspection scheduled"
    if vehicle.auctions.filter(status=Auction.Status.CLOSED).exists():
        return "Decision needed"
    return vehicle.get_status_display()


@login_required(login_url="/app/login/")
def app_seller_home(request):
    u = request.user
    # Loop-safe role guard (never bounce a staff user into a redirect ping-pong).
    if u.is_dealer:
        return redirect("/app/dealer/")
    if not u.is_seller:
        return redirect(get_dashboard_url(u))

    cars = []
    for v in Vehicle.objects.filter(seller=u).order_by("-id"):
        live_auction = v.auctions.filter(status=Auction.Status.LIVE).order_by("-start_at").first()
        high_base = None
        if live_auction is not None:
            hb = live_auction.highest_bid  # Bid object or None (GROSS)
            if hb is not None:
                # Seller must never see gross — de-gross the live top bid to BASE.
                high_base = base_from_gross(hb.amount)["base"]
        cars.append({
            "id": v.id,
            "name": v.display_name,
            "plate": v.plate_number,
            "grade": v.condition_grade,
            "status_label": _seller_status_label(v, live_auction),
            "is_live": live_auction is not None,
            "expected_fmt": _inr(v.expected_price),   # seller BASE
            "high_base_fmt": _inr(high_base),         # live top bid in BASE, or None
        })

    return render(request, "www/app/seller_home.html", {
        "first_name": u.first_name,
        "cars": cars,
    })


# ── 4. Dealer home ─────────────────────────────────────────────────────────────
@login_required(login_url="/app/login/")
def app_dealer_home(request):
    u = request.user
    if u.is_seller:
        return redirect("/app/seller/")
    if not u.is_dealer:
        return redirect(get_dashboard_url(u))

    now = timezone.now()
    live_qs = _live_auction_qs()
    live_count = live_qs.count()
    open_ocb_count = open_round_listings().count()
    ending_15 = live_qs.filter(end_at__gt=now, end_at__lte=now + timedelta(minutes=15)).count()

    ending_soon = []
    for a in live_qs.select_related("vehicle").order_by("end_at")[:3]:
        hb = a.highest_bid  # Bid object or None (GROSS)
        bidders = (a.bids.filter(is_voided=False, created_at__gte=a.start_at)
                   .values("dealer_id").distinct().count())
        ending_soon.append({
            "id": a.id,
            "name": a.vehicle.display_name,
            "grade": a.vehicle.condition_grade,
            "high_gross_fmt": _inr(hb.amount if hb is not None else a.reserve_price),  # dealer sees GROSS
            "has_bid": hb is not None,
            "bidders": bidders,
            "end_ts": int(a.end_at.timestamp()),
        })

    # Leading vs outbid across the live auctions this dealer has bid on.
    leading = outbid = 0
    my_live = (Auction.objects.filter(status=Auction.Status.LIVE,
                                       bids__dealer=u, bids__is_voided=False)
               .distinct())
    for a in my_live:
        hb = a.highest_bid
        if hb is not None and hb.dealer_id == u.id:
            leading += 1
        else:
            outbid += 1

    profile = getattr(u, "dealer_profile", None)
    greeting_name = (getattr(profile, "dealership_name", "") or u.first_name or "").strip()

    return render(request, "www/app/dealer_home.html", {
        "greeting_name": greeting_name,
        "live_count": live_count,
        "open_ocb_count": open_ocb_count,
        "ending_15": ending_15,
        "ending_soon": ending_soon,
        "leading": leading,
        "outbid": outbid,
    })
