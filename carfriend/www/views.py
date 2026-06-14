import json
import re
import time

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from . import services
from .models import HomepageLead

# Indian plate formats: e.g. GJ05MK2024, MH12AB1234, DL3CAB1234, and the
# newer BH-series like 22BH1234AA. Kept deliberately permissive.
PLATE_RE = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{1,4}$")
BH_PLATE_RE = re.compile(r"^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$")
PHONE_RE = re.compile(r"^[6-9][0-9]{9}$")

# Basic rate limit for the lookup endpoint (per client IP).
ESTIMATE_MAX_PER_WINDOW = 15
ESTIMATE_WINDOW_SECONDS = 60
ESTIMATE_MIN_INTERVAL = 1.5  # server-side debounce between two calls


def _client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _rate_limited(request):
    """Return a friendly message if the caller is going too fast, else None."""
    ip = _client_ip(request)
    now = time.time()

    last_key = f"est_last:{ip}"
    last = cache.get(last_key)
    if last and (now - last) < ESTIMATE_MIN_INTERVAL:
        return "You're going a little fast — please wait a moment and try again."
    cache.set(last_key, now, ESTIMATE_WINDOW_SECONDS)

    count_key = f"est_count:{ip}"
    count = cache.get(count_key, 0)
    if count >= ESTIMATE_MAX_PER_WINDOW:
        return "Too many lookups right now. Please try again in a minute."
    cache.set(count_key, count + 1, ESTIMATE_WINDOW_SECONDS)
    return None


def _normalise_plate(plate):
    return (plate or "").upper().replace(" ", "").replace("-", "").strip()


def _valid_plate(plate):
    return bool(PLATE_RE.match(plate) or BH_PLATE_RE.match(plate))


FALLBACK_HINT = "Couldn't fetch your car automatically — try selecting your brand instead."


@require_POST
def estimate_price(request):
    """Validate a plate (or a manual make/model/year), look up the vehicle via
    Surepass when a plate is given, and return an estimated price band.

    Returns ONLY make/model/year/fuel + price band — never owner details.
    """
    limited = _rate_limited(request)
    if limited:
        return JsonResponse({"ok": False, "error": limited}, status=429)

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}

    plate = _normalise_plate(body.get("plate_number"))
    source = "plate"
    vehicle = None

    if plate:
        if not _valid_plate(plate):
            return JsonResponse(
                {"ok": False, "error": "That doesn't look like a valid number plate. "
                                       "Please check and try again, or select your brand.",
                 "fallback": True},
                status=400,
            )
        try:
            vehicle = services.lookup_rc(plate)
        except services.SurepassNotFound:
            return JsonResponse(
                {"ok": False, "error": "We couldn't find that car. " + FALLBACK_HINT,
                 "fallback": True},
                status=404,
            )
        except services.SurepassTimeout:
            return JsonResponse(
                {"ok": False, "error": "The lookup service is slow right now. " + FALLBACK_HINT,
                 "fallback": True},
                status=504,
            )
        except services.SurepassError:
            return JsonResponse(
                {"ok": False, "error": "Something went wrong fetching your car. " + FALLBACK_HINT,
                 "fallback": True},
                status=502,
            )
    else:
        # Manual brand → model → year fallback path.
        source = "brand"
        make = (body.get("make") or "").strip()
        model = (body.get("model") or "").strip()
        year = (body.get("year") or "").strip()
        if not (make and model and year):
            return JsonResponse(
                {"ok": False, "error": "Please enter a number plate, or pick a brand, model and year."},
                status=400,
            )
        vehicle = {"make": make.title(), "model": model.title(),
                   "year": int(year) if year.isdigit() else None,
                   "fuel": (body.get("fuel") or "").strip().title()}

    low, high = services.estimate_price_band(
        vehicle.get("make"), vehicle.get("model"), vehicle.get("year"), vehicle.get("fuel"))

    return JsonResponse({
        "ok": True,
        "source": source,
        "vehicle": {
            "make": vehicle.get("make") or "",
            "model": vehicle.get("model") or "",
            "year": vehicle.get("year"),
            "fuel": vehicle.get("fuel") or "",
        },
        "price": {"low": low, "high": high},
        # echo back the (normalised) plate so the lead capture can store it
        "plate_number": plate,
    })


@require_POST
def capture_lead(request):
    """Persist a homepage lead (car details + phone) as a HomepageLead."""
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}

    phone = re.sub(r"[^0-9]", "", body.get("phone") or "")
    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    if not PHONE_RE.match(phone):
        return JsonResponse(
            {"ok": False, "error": "Please enter a valid 10-digit mobile number."},
            status=400,
        )

    year = body.get("year")
    try:
        year = int(year) if year not in (None, "", "null") else None
    except (TypeError, ValueError):
        year = None

    source = body.get("source")
    source = source if source in (HomepageLead.SOURCE_PLATE, HomepageLead.SOURCE_BRAND) \
        else HomepageLead.SOURCE_PLATE

    price = body.get("price") if isinstance(body.get("price"), dict) else {}

    def _band(val):
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    HomepageLead.objects.create(
        plate_number=_normalise_plate(body.get("plate_number"))[:20],
        make=(body.get("make") or "")[:100],
        model=(body.get("model") or "")[:100],
        year=year,
        fuel_type=(body.get("fuel") or "")[:30],
        phone=phone,
        est_price_low=_band(price.get("low")),
        est_price_high=_band(price.get("high")),
        source=source,
    )
    return JsonResponse({"ok": True, "message": "Thanks! Our team will call you with your best offer."})


def index(request):
    return render(request, "www/index.html")


def how_it_works(request):
    return render(request, "www/how_it_works.html")


def about(request):
    return render(request, "www/about.html")


def contact(request):
    return render(request, "www/contact.html")


def terms(request):
    return render(request, "www/policies/terms.html")


def privacy(request):
    return render(request, "www/policies/privacy.html")


def cookies(request):
    return render(request, "www/policies/cookies.html")


def auction_rules(request):
    return render(request, "www/policies/auction_rules.html")


def seller_agreement(request):
    return render(request, "www/policies/seller_agreement.html")


def refund_policy(request):
    return render(request, "www/policies/refund_policy.html")


def kyc_policy(request):
    return render(request, "www/policies/kyc_policy.html")


def inspection_policy(request):
    return render(request, "www/policies/inspection_policy.html")


def grievance(request):
    return render(request, "www/policies/grievance.html")
