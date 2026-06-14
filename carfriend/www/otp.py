"""Phone OTP service for the guest sell-your-car flow.

Design goal: enabling real SMS is JUST setting FAST2SMS_API_KEY in the
environment — no code change.

- FAST2SMS_API_KEY empty  -> STUB MODE: a generated OTP is logged server-side
  and the fixed code "000000" is accepted for any phone (handy for demos/tests).
- FAST2SMS_API_KEY set     -> the real Fast2SMS OTP endpoint is called.

The key is read from the environment and never leaves the server. OTP codes and
rate-limit counters live in Django's cache (never in templates/JS).
"""

import logging
import os
import random
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from django.core.cache import cache
from dotenv import load_dotenv

# Load /var/www/carfriend/.env (one level above the Django project root) so
# FAST2SMS_API_KEY resolves via os.environ. override=False keeps real env vars.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger(__name__)

STUB_CODE = "000000"
OTP_TTL_SECONDS = 300          # a code is valid for 5 minutes
MAX_VERIFY_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60   # one send per phone per minute
FAST2SMS_OTP_URL = "https://www.fast2sms.com/dev/bulkV2"


def _api_key():
    # Read fresh each call so the mode flips the moment the env var is set.
    return os.environ.get("FAST2SMS_API_KEY", "").strip()


def is_stub_mode():
    return not _api_key()


def _otp_key(phone):
    return f"otp:{phone}"


def _rate_key(phone):
    return f"otp_rate:{phone}"


def _generate_code():
    return f"{random.randint(0, 999999):06d}"


class OTPError(Exception):
    """Base error for OTP send failures."""


class OTPRateLimited(OTPError):
    """Raised when a phone requests OTPs too quickly."""


def send_otp(phone):
    """Generate + deliver an OTP for ``phone``.

    Returns a dict {"ok": True, "mode": "stub"|"live"}.
    Raises OTPRateLimited if called more than once per cooldown window.
    """
    if cache.get(_rate_key(phone)):
        raise OTPRateLimited("Please wait a minute before requesting another OTP.")
    cache.set(_rate_key(phone), True, RESEND_COOLDOWN_SECONDS)

    code = _generate_code()
    cache.set(_otp_key(phone), {"code": code, "attempts": 0}, OTP_TTL_SECONDS)

    if is_stub_mode():
        # STUB: log the code; "000000" is also accepted by verify_otp.
        logger.info("[OTP stub] phone=%s code=%s (stub also accepts %s)", phone, code, STUB_CODE)
        return {"ok": True, "mode": "stub"}

    _send_via_fast2sms(phone, code)
    return {"ok": True, "mode": "live"}


def _send_via_fast2sms(phone, code):
    """Call the real Fast2SMS OTP endpoint. Never logs the API key.

    TODO: confirm the exact route/params for your Fast2SMS plan; this uses the
    documented OTP route.
    """
    params = urllib.parse.urlencode({
        "route": "otp",
        "variables_values": code,
        "numbers": phone,
    })
    url = f"{FAST2SMS_OTP_URL}?{params}"
    req = urllib.request.Request(url, method="GET", headers={
        "authorization": _api_key(),
        "accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        logger.warning("Fast2SMS OTP HTTP error: status=%s", exc.code)
        raise OTPError("Could not send OTP right now. Please try again.") from None
    except (socket.timeout, TimeoutError, urllib.error.URLError) as exc:
        logger.warning("Fast2SMS OTP connection error: %s", getattr(exc, "reason", exc))
        raise OTPError("Could not reach the SMS service. Please try again.") from None


def verify_otp(phone, code):
    """Return True if ``code`` is valid for ``phone``.

    In stub mode the fixed STUB_CODE always passes. Otherwise the code must match
    the last one sent and be within the attempt/TTL limits.
    """
    code = (code or "").strip()

    if is_stub_mode() and code == STUB_CODE:
        return True

    rec = cache.get(_otp_key(phone))
    if not rec:
        return False
    if rec.get("attempts", 0) >= MAX_VERIFY_ATTEMPTS:
        cache.delete(_otp_key(phone))
        return False

    if code and code == rec.get("code"):
        cache.delete(_otp_key(phone))
        return True

    rec["attempts"] = rec.get("attempts", 0) + 1
    cache.set(_otp_key(phone), rec, OTP_TTL_SECONDS)
    return False
