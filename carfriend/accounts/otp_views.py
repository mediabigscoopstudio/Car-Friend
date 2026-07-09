"""Phone-OTP auth endpoints for the mobile apps (NEW, additive, parallel path).

Deliberately separate from the website's existing Google + email/password login
(accounts.views) and from the older cache-based sell-flow OTP (www/otp.py). These two
endpoints are the app's whole auth surface: request an OTP, then verify it to get a
logged-in session (Set-Cookie: sessionid). CSRF-exempt (the app has no CSRF token) and
rate-limited instead. The OTP code is NEVER returned to the client nor logged.
"""
import json
import logging
import random
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login as auth_login
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.guest import normalise_phone
from accounts.models import OTPVerification, Role, User

logger = logging.getLogger(__name__)

FAST2SMS_URL = "https://www.fast2sms.com/dev/bulkV2"
OTP_TTL_MINUTES = 5
MAX_PER_HOUR = 5


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except (ValueError, TypeError):
        return {}


def _valid_mobile(phone):
    """10-digit Indian mobile starting 6–9."""
    return len(phone) == 10 and phone[0] in "6789"


def _send_fast2sms(phone, code):
    """Send the OTP via Fast2SMS. Returns (ok, message). Never logs the code."""
    api_key = getattr(settings, "CF_FAST2SMS_API_KEY", "")
    if not api_key:
        return False, "SMS is not configured."
    params = {
        "route": "otp",
        "variables_values": code,
        "numbers": phone,
        "sender_id": getattr(settings, "CF_FAST2SMS_SENDER_ID", "CRFRND"),
    }
    req = urllib.request.Request(
        FAST2SMS_URL + "?" + urllib.parse.urlencode(params), method="POST",
        headers={"authorization": api_key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        logger.warning("Fast2SMS HTTP error status=%s", exc.code)
    except Exception as exc:
        logger.warning("Fast2SMS connection error: %s", exc)
        return False, "Could not reach the SMS service."
    try:
        body = json.loads(raw)
    except ValueError:
        body = {}
    if body.get("return") is True:
        return True, "sent"
    msg = body.get("message")
    return False, (msg if isinstance(msg, str) else "Could not send OTP. Please try again.")


@csrf_exempt
@require_POST
def otp_request(request):
    """POST {"phone": "9876543210"} → {"success": true, "message": "OTP sent"}.
    The OTP is never returned. test mode stores CF_OTP_TEST_CODE; live sends via Fast2SMS."""
    phone = normalise_phone(_json_body(request).get("phone"))
    if not _valid_mobile(phone):
        return JsonResponse({"success": False, "error": "Enter a valid 10-digit mobile number."}, status=400)

    hour_ago = timezone.now() - timedelta(hours=1)
    if OTPVerification.objects.filter(phone=phone, created_at__gte=hour_ago).count() >= MAX_PER_HOUR:
        return JsonResponse({"success": False, "error": "Too many OTP requests. Please try again later."}, status=429)

    if getattr(settings, "CF_OTP_MODE", "test") == "live":
        code = f"{random.randint(0, 999999):06d}"
        ok, msg = _send_fast2sms(phone, code)
        if not ok:
            return JsonResponse({"success": False, "error": f"SMS: {msg}"}, status=502)
    else:
        code = str(getattr(settings, "CF_OTP_TEST_CODE", "000000"))

    OTPVerification.objects.create(phone=phone, otp_code=code)
    logger.info("OTP requested phone=%s at %s", phone, timezone.now().isoformat(timespec="seconds"))
    return JsonResponse({"success": True, "message": "OTP sent"})


def _get_or_create_phone_user(phone, role):
    """Find the phone-keyed user, else create a minimal real account. Role is applied ONLY
    when creating; an existing user's role is never changed."""
    existing = User.objects.filter(phone=phone).order_by("is_guest", "id").first()
    if existing:
        if not existing.phone_verified:
            existing.phone_verified = True
            existing.save(update_fields=["phone_verified"])
        return existing
    role_val = Role.DEALER if role == "dealer" else Role.SELLER
    username = base = f"u{phone}"
    n = 0
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"{base}_{n}"
    user = User(username=username, phone=phone, phone_verified=True, is_guest=False, role=role_val)
    user.set_unusable_password()
    user.save()
    logger.info("Created phone-OTP account user id=%s role=%s", user.id, role_val)
    return user


@csrf_exempt
@require_POST
def otp_verify(request):
    """POST {"phone", "otp", "role"?} → log in + {"success", "user_id", "role", "redirect"}.
    role (seller|dealer) is used ONLY when the account is first created."""
    body = _json_body(request)
    phone = normalise_phone(body.get("phone"))
    code = (body.get("otp") or "").strip()
    role = (body.get("role") or "seller").strip().lower()
    if not _valid_mobile(phone) or not code:
        return JsonResponse({"success": False, "error": "Phone and OTP are required."}, status=400)

    rec = OTPVerification.objects.filter(phone=phone, verified=False).order_by("-created_at").first()
    if not rec or rec.otp_code != code:
        return JsonResponse({"success": False, "error": "Invalid OTP"}, status=400)
    if rec.is_expired:
        return JsonResponse({"success": False, "error": "OTP expired"}, status=400)

    rec.verified = True
    rec.save(update_fields=["verified"])

    user = _get_or_create_phone_user(phone, role)
    # Explicit backend — multiple AUTHENTICATION_BACKENDS are configured (ModelBackend + allauth).
    auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    dest = "/auth/dealer/dashboard/" if user.role == Role.DEALER else "/auth/seller/dashboard/"
    return JsonResponse({"success": True, "user_id": user.id, "role": user.role, "redirect": dest})
