"""Vehicle RC lookup via the Surepass RC API.

Security notes:
- The bearer token is read ONLY from SUREPASS_TOKEN, via python-decouple
  (a real env var, or a key in the gitignored .env). The .env is loaded into the
  environment in settings.py (top of file), so the token is available on every
  code path. The token is never written to a template, JS, or committed file.
- This module is the only place that talks to Surepass; the browser never does.
- lookup_rc() returns ONLY make/model/year/fuel. lookup_rc_full() returns the
  full RC detail set the sell flow needs (incl. the owner name) — the caller is
  responsible for masking the owner name before sending anything to the client
  and for keeping the full record server-side only.

NOTE: there is TEMPORARY debug logging of the Surepass status + body in
_call_surepass_rc (marked "[TEMP surepass]"). Remove it once the lookup is
verified in production — the body can contain owner PII.
"""

import datetime
import json
import logging
import socket
import urllib.error
import urllib.request

from decouple import config

logger = logging.getLogger(__name__)

# RC endpoint path — adjust if your Surepass plan exposes a different route
# (e.g. rc-lite). This is the documented RC verification path.
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


# ── parsing helpers ──────────────────────────────────────────────────────────

def _extract_year(data):
    for key in ("manufacturing_date_formatted", "manufacturing_date",
                "registration_date", "reg_date"):
        val = data.get(key)
        if not val:
            continue
        digits = "".join(c for c in str(val) if c.isdigit())
        for i in range(0, max(1, len(digits) - 3)):
            chunk = digits[i:i + 4]
            if len(chunk) == 4 and 1980 <= int(chunk) <= datetime.date.today().year + 1:
                return int(chunk)
    return None


def _norm_fuel(raw):
    s = (raw or "").strip().lower()
    if not s:
        return ""
    if "diesel" in s:
        return "diesel"
    if "cng" in s:
        return "cng"
    if "electric" in s or s == "ev":
        return "electric"
    if "hybrid" in s:
        return "hybrid"
    return "petrol"


def _norm_transmission(raw):
    s = (raw or "").strip().lower()
    if any(k in s for k in ("auto", "amt", "cvt", "dct", "torque")):
        return "automatic"
    if "manual" in s:
        return "manual"
    return ""


def _iso_date(raw):
    s = (raw or "").strip()
    if not s:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d-%b-%Y", "%d-%B-%Y", "%d-%b-%y"):
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _int_or(raw, default=1):
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


# ── Surepass call ────────────────────────────────────────────────────────────

def _call_surepass_rc(plate_number):
    """POST the plate to Surepass and return the response 'data' dict.

    Raises a SurepassError subclass on any failure.
    """
    token = config("SUREPASS_TOKEN", default="")
    if not token:
        logger.error("SUREPASS_TOKEN is not set; RC lookup unavailable.")
        raise SurepassConfigError("RC lookup is not configured.")

    url = SUREPASS_BASE + RC_ENDPOINT
    body = json.dumps({"id_number": plate_number}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        # TEMP debug logging — remove once verified (body may contain PII).
        logger.warning("[TEMP surepass] id_number=%s status=%s body=%s", plate_number, exc.code, raw[:2000])
        if exc.code in (404, 422):
            raise SurepassNotFound("No vehicle found for that number plate.") from None
        raise SurepassError("RC lookup failed. Please try again.") from None
    except (socket.timeout, TimeoutError):
        logger.warning("[TEMP surepass] id_number=%s status=timeout after %ss", plate_number, TIMEOUT_SECONDS)
        raise SurepassTimeout("RC lookup timed out.") from None
    except urllib.error.URLError as exc:
        logger.warning("[TEMP surepass] id_number=%s status=urlerror body=%s", plate_number, exc.reason)
        raise SurepassTimeout("Could not reach the RC service.") from None

    # TEMP debug logging — remove once verified (body may contain PII).
    logger.warning("[TEMP surepass] id_number=%s status=%s body=%s", plate_number, status, raw[:2000])

    try:
        payload = json.loads(raw)
    except ValueError:
        logger.warning("Surepass RC returned non-JSON response.")
        raise SurepassError("RC lookup failed. Please try again.") from None

    data = (payload or {}).get("data") or {}
    if not data:
        raise SurepassNotFound("No vehicle found for that number plate.")
    return data


def lookup_rc(plate_number):
    """Slim lookup: returns ONLY {make, model, year, fuel} (no PII)."""
    data = _call_surepass_rc(plate_number)
    make = data.get("maker_description") or data.get("brand_name") or data.get("make") or ""
    model = data.get("maker_model") or data.get("model") or data.get("vehicle_model") or ""
    fuel = data.get("fuel_type") or data.get("fuel") or ""
    return {
        "make": str(make).strip().title(),
        "model": str(model).strip().title(),
        "year": _extract_year(data),
        "fuel": str(fuel).strip().title(),
    }


def lookup_rc_full(plate_number):
    """Full lookup for the sell flow. Returns every RC field the flow persists.

    INCLUDES the real owner_name — the caller MUST mask it before sending to the
    client and keep this dict server-side only.
    """
    data = _call_surepass_rc(plate_number)

    make = data.get("maker_description") or data.get("brand_name") or data.get("make") or ""
    model = data.get("maker_model") or data.get("model") or data.get("vehicle_model") or ""
    variant = data.get("variant") or data.get("vehicle_variant") or ""
    colour = data.get("color") or data.get("colour") or data.get("vehicle_colour") or ""
    rto = data.get("registered_at") or data.get("rto") or ""
    reg_state = data.get("state") or data.get("registration_state") or ""
    owner_name = data.get("owner_name") or ""
    chassis = data.get("vehicle_chasi_number") or data.get("chassis_number") or data.get("chasi_number") or ""
    engine = data.get("vehicle_engine_number") or data.get("engine_number") or ""
    financer = str(data.get("financer") or "").strip()
    financed = data.get("financed")
    is_hyp = bool(financed) if financed is not None else bool(financer and financer.upper() not in ("NA", "N/A", "NONE"))

    return {
        "make":                 str(make).strip().title(),
        "model":                str(model).strip().title(),
        "variant":              str(variant).strip(),
        "year":                 _extract_year(data),
        "fuel_type":            _norm_fuel(data.get("fuel_type") or data.get("fuel")),
        "transmission":         _norm_transmission(data.get("transmission")),
        "colour":               str(colour).strip().title(),
        "registration_date":    _iso_date(data.get("registration_date")),
        "registration_state":   str(reg_state).strip(),
        "rto":                  str(rto).strip(),
        "owner_name":           str(owner_name).strip(),   # REAL name — mask in the view
        "owner_number":         _int_or(data.get("owner_number"), 1),
        "chassis_number":       str(chassis).strip(),
        "engine_number":        str(engine).strip(),
        "insurance_valid_till": _iso_date(data.get("insurance_upto") or data.get("insurance_valid_till")),
        "is_hypothecated":      is_hyp,
        "accident_history":     False,   # not available from RC
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
    age = max(0, datetime.date.today().year - year) if year else 6
    value = base * (0.88 ** age)

    if (fuel or "").lower().startswith("diesel"):
        value *= 1.05

    low = int(round(value * 0.90 / 1000.0)) * 1000
    high = int(round(value * 1.10 / 1000.0)) * 1000
    low = max(low, 25000)
    high = max(high, low + 25000)
    return low, high
