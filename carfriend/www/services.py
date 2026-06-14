"""Vehicle RC lookup via the Surepass RC API.

Security notes:
- The bearer token is read ONLY from SUREPASS_TOKEN, via python-decouple
  (the project's config mechanism: a real env var, or a key in the gitignored
  .env file). It is never written to a template, JS, log line, or committed file.
- This module is the only place that talks to Surepass; the browser never does.
- We deliberately return ONLY make / model / year / fuel to the caller. The RC
  response also contains the registered owner's name, father's name, address,
  etc. — that personal data is never returned to the client and never logged.
"""

import datetime
import json
import logging
import socket
import urllib.error
import urllib.request
from pathlib import Path

from decouple import config
from dotenv import load_dotenv

# Load the project's .env (one level above the Django project root, i.e.
# /var/www/carfriend/.env) so SUREPASS_TOKEN resolves. override=False (the
# default) means real environment variables are not clobbered. decouple.config()
# reads os.environ first, so the token loaded here is picked up at line ~70.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger(__name__)

# Sandbox base per spec. RC endpoint path — adjust if your Surepass plan exposes
# a different route (e.g. rc-lite). Marked as the documented RC verification path.
SUREPASS_BASE = config("SUREPASS_BASE_URL", default="https://sandbox.surepass.app")
RC_ENDPOINT = "/api/v1/rc/rc-full"
TIMEOUT_SECONDS = 8


class SurepassError(Exception):
    """Base error for any RC lookup failure (network, auth, parsing)."""


class SurepassConfigError(SurepassError):
    """Raised when SUREPASS_TOKEN is not configured."""


class SurepassTimeout(SurepassError):
    """Raised when the upstream call times out or is unreachable."""


class SurepassNotFound(SurepassError):
    """Raised when no vehicle matches the supplied plate."""


def _extract_year(data):
    for key in ("manufacturing_date_formatted", "manufacturing_date",
                "registration_date", "reg_date"):
        val = data.get(key)
        if not val:
            continue
        # values look like "2022-05-01", "05/2022", or "2022"
        digits = "".join(c for c in str(val) if c.isdigit())
        for chunk_len in (4,):
            for i in range(0, max(1, len(digits) - chunk_len + 1)):
                chunk = digits[i:i + chunk_len]
                if len(chunk) == 4 and 1980 <= int(chunk) <= datetime.date.today().year + 1:
                    return int(chunk)
    return None


def lookup_rc(plate_number):
    """Look up an Indian RC by plate number.

    Returns a dict with ONLY non-personal vehicle fields:
        {"make": str, "model": str, "year": int|None, "fuel": str}
    Raises a SurepassError subclass on any failure.
    """
    token = config("SUREPASS_TOKEN", default="")
    if not token:
        # No PII here; safe to log.
        logger.error("SUREPASS_TOKEN is not set; RC lookup unavailable.")
        raise SurepassConfigError("RC lookup is not configured.")

    url = SUREPASS_BASE + RC_ENDPOINT
    body = json.dumps({"id_number": plate_number}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # Do not log the response body (may contain PII). Log status only.
        logger.warning("Surepass RC HTTP error: status=%s", exc.code)
        if exc.code in (404, 422):
            raise SurepassNotFound("No vehicle found for that number plate.") from None
        raise SurepassError("RC lookup failed. Please try again.") from None
    except (socket.timeout, TimeoutError):
        logger.warning("Surepass RC timeout after %ss", TIMEOUT_SECONDS)
        raise SurepassTimeout("RC lookup timed out.") from None
    except urllib.error.URLError as exc:
        logger.warning("Surepass RC connection error: %s", exc.reason)
        raise SurepassTimeout("Could not reach the RC service.") from None

    try:
        payload = json.loads(raw)
    except ValueError:
        logger.warning("Surepass RC returned non-JSON response.")
        raise SurepassError("RC lookup failed. Please try again.") from None

    data = (payload or {}).get("data") or {}
    if not data:
        raise SurepassNotFound("No vehicle found for that number plate.")

    make = data.get("maker_description") or data.get("brand_name") or data.get("make") or ""
    model = data.get("maker_model") or data.get("model") or data.get("vehicle_model") or ""
    fuel = data.get("fuel_type") or data.get("fuel") or ""
    year = _extract_year(data)

    # Return ONLY the four non-personal fields.
    return {
        "make": str(make).strip().title(),
        "model": str(model).strip().title(),
        "year": year,
        "fuel": str(fuel).strip().title(),
    }


def estimate_price_band(make, model, year, fuel):
    """Placeholder valuation.

    TODO: replace with real pricing logic (market data / valuation model /
    inspection-grade adjustments). For now this is a crude age-based
    depreciation purely so the UI has a number to show.
    """
    try:
        year = int(year) if year else None
    except (TypeError, ValueError):
        year = None

    base = 800000  # TODO: derive from make/model instead of a flat base
    if year:
        age = max(0, datetime.date.today().year - year)
    else:
        age = 6
    value = base * (0.88 ** age)

    # Fuel nudge — purely illustrative placeholder.
    if (fuel or "").lower().startswith("diesel"):
        value *= 1.05

    low = int(round(value * 0.90 / 1000.0)) * 1000
    high = int(round(value * 1.10 / 1000.0)) * 1000
    low = max(low, 25000)
    high = max(high, low + 25000)
    return low, high
