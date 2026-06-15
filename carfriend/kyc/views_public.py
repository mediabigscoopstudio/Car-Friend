"""Public (seller-facing) KYC flow — PAN + Aadhaar via Surepass.

Stores only status + masked identifier + provider-returned name. The raw
Aadhaar number is never stored. Endpoints are rate-limited per user.
"""

import json
import re
import time

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from www import services
from .models import KYCVerification

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")

RATE_MAX = 8            # max verify attempts per window
RATE_WINDOW = 300       # 5 minutes
RATE_MIN_INTERVAL = 2   # seconds between calls


def _rate_limited(request, bucket):
    key_last = f"kyc_last:{bucket}:{request.user.id}"
    key_cnt = f"kyc_cnt:{bucket}:{request.user.id}"
    now = time.time()
    last = cache.get(key_last)
    if last and (now - last) < RATE_MIN_INTERVAL:
        return "Please wait a moment and try again."
    cache.set(key_last, now, RATE_WINDOW)
    cnt = cache.get(key_cnt, 0)
    if cnt >= RATE_MAX:
        return "Too many attempts. Please try again later."
    cache.set(key_cnt, cnt + 1, RATE_WINDOW)
    return None


def _status_for(user, kind):
    rec = KYCVerification.objects.filter(subject=user, kind=kind).order_by("-created_at").first()
    return rec.status if rec else None


def _refresh_kyc_done(user):
    pan_ok = _status_for(user, KYCVerification.Kind.PAN) == KYCVerification.Status.APPROVED
    aad_ok = _status_for(user, KYCVerification.Kind.AADHAAR) == KYCVerification.Status.APPROVED
    done = pan_ok and aad_ok
    if user.is_kyc_done != done:
        user.is_kyc_done = done
        user.save(update_fields=["is_kyc_done"])
    return done


@login_required(login_url="/auth/login/")
def kyc_page(request):
    ctx = {
        "pan_status":     _status_for(request.user, KYCVerification.Kind.PAN),
        "aadhaar_status": _status_for(request.user, KYCVerification.Kind.AADHAAR),
    }
    return render(request, "www/kyc/verify.html", ctx)


@login_required(login_url="/auth/login/")
@require_POST
def pan_verify(request):
    limited = _rate_limited(request, "pan")
    if limited:
        return JsonResponse({"ok": False, "error": limited}, status=429)

    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    pan = (body.get("pan") or "").upper().strip()
    if not PAN_RE.match(pan):
        return JsonResponse({"ok": False, "error": "Enter a valid PAN (e.g. ABCDE1234F)."}, status=400)

    try:
        result = services.pan_comprehensive(pan)
    except services.SurepassNotFound:
        return JsonResponse({"ok": False, "error": "No record found for that PAN. Please check and retry."}, status=404)
    except services.SurepassConfigError:
        return JsonResponse({"ok": False, "error": "Verification is temporarily unavailable."}, status=503)
    except services.SurepassError:
        return JsonResponse({"ok": False, "error": "PAN verification failed. Please try again."}, status=502)

    seller_name = request.user.get_full_name() or request.user.username
    matched = services.names_match(result["name"], seller_name)
    # If we have no name on file we cannot compare — accept the PAN holder's name.
    if not (request.user.get_full_name() or "").strip():
        matched = True
    status = KYCVerification.Status.APPROVED if matched else KYCVerification.Status.REJECTED

    KYCVerification.objects.create(
        subject=request.user,
        kind=KYCVerification.Kind.PAN,
        status=status,
        provider_ref=result["ref"],
        masked_value=result["pan_masked"],
        result_name=result["name"],
        note="" if matched else "PAN name did not match the account name.",
    )
    _refresh_kyc_done(request.user)

    if matched:
        return JsonResponse({"ok": True, "status": status, "name": result["name"]})
    return JsonResponse({"ok": False, "status": status,
                         "error": "The name on this PAN doesn't match your account. Please use your own PAN."}, status=400)


@login_required(login_url="/auth/login/")
@require_POST
def aadhaar_start(request):
    limited = _rate_limited(request, "aadhaar")
    if limited:
        return JsonResponse({"ok": False, "error": limited}, status=429)

    redirect_url = request.build_absolute_uri(reverse("kyc_aadhaar_callback"))
    try:
        result = services.digilocker_initialize(redirect_url)
    except services.SurepassConfigError:
        return JsonResponse({"ok": False, "error": "Verification is temporarily unavailable."}, status=503)
    except services.SurepassError:
        return JsonResponse({"ok": False, "error": "Could not start Aadhaar verification. Please try again."}, status=502)

    if not result.get("url"):
        return JsonResponse({"ok": False, "error": "Could not start Aadhaar verification. Please try again."}, status=502)

    request.session["kyc_aadhaar_client_id"] = result["client_id"]
    request.session.modified = True
    return JsonResponse({"ok": True, "url": result["url"]})


@login_required(login_url="/auth/login/")
def aadhaar_callback(request):
    """Return target after Digilocker. Fetch the Aadhaar result and store it."""
    client_id = request.session.get("kyc_aadhaar_client_id")
    if not client_id:
        return redirect("/kyc/?aadhaar=error")
    try:
        result = services.digilocker_fetch_aadhaar(client_id)
    except services.SurepassError:
        return redirect("/kyc/?aadhaar=error")

    KYCVerification.objects.create(
        subject=request.user,
        kind=KYCVerification.Kind.AADHAAR,
        status=KYCVerification.Status.APPROVED,
        provider_ref=result["ref"],
        masked_value=result["aadhaar_masked"],   # masked only; raw never stored
        result_name=result["name"],
    )
    request.session.pop("kyc_aadhaar_client_id", None)
    _refresh_kyc_done(request.user)
    return redirect("/kyc/?aadhaar=ok")
