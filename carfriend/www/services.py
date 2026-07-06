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

NOTE: Surepass response bodies are never logged — they can contain owner PII.
Only non-identifying status codes and error reasons are logged.
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
        # Never log id_number or the response body — both can carry PII.
        logger.warning("Surepass RC HTTP error: status=%s", exc.code)
        if exc.code in (404, 422):
            raise SurepassNotFound("No vehicle found for that number plate.") from None
        raise SurepassError("RC lookup failed. Please try again.") from None
    except (socket.timeout, TimeoutError):
        logger.warning("Surepass RC timed out after %ss", TIMEOUT_SECONDS)
        raise SurepassTimeout("RC lookup timed out.") from None
    except urllib.error.URLError as exc:
        logger.warning("Surepass RC connection error: %s", exc.reason)
        raise SurepassTimeout("Could not reach the RC service.") from None

    # Response body intentionally NOT logged — it contains owner PII.
    logger.info("Surepass RC response: status=%s", status)

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


# ── Seller KYC: PAN + Aadhaar (Surepass) ─────────────────────────────────────
# Reuses the same plumbing as the RC lookup: SUREPASS_TOKEN from env, sandbox
# base URL. Response bodies are never logged (they carry PAN/Aadhaar PII);
# only status codes and error reasons are.

PAN_ENDPOINT = "/api/v1/pan/pan-comprehensive"
DIGILOCKER_INIT_ENDPOINT = "/api/v1/digilocker/initialize"
DIGILOCKER_AADHAAR_ENDPOINT = "/api/v1/digilocker/download-aadhaar"


def _call_surepass(path, payload=None, tag="kyc", method="POST", timeout=None):
    """Generic Surepass call. Returns (status_code, parsed_json_dict).

    Raises a SurepassError subclass on any failure. Never logs the response
    body (it can contain PAN/Aadhaar PII); only status codes / error reasons.
    """
    token = config("SUREPASS_TOKEN", default="")
    if not token:
        logger.error("SUREPASS_TOKEN is not set; %s unavailable.", tag)
        raise SurepassConfigError("Verification is not configured.")

    timeout = timeout or TIMEOUT_SECONDS
    url = SUREPASS_BASE + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        # Never log the response body — PAN/Aadhaar/challan responses carry PII.
        logger.warning("Surepass %s HTTP error: status=%s", tag, exc.code)
        if exc.code in (401, 403):
            raise SurepassConfigError("Verification auth failed.") from None
        if exc.code in (404, 422):
            raise SurepassNotFound("No matching record found.") from None
        raise SurepassError("Verification failed. Please try again.") from None
    except (socket.timeout, TimeoutError):
        logger.warning("Surepass %s timed out after %ss", tag, timeout)
        raise SurepassTimeout("Verification timed out.") from None
    except urllib.error.URLError as exc:
        logger.warning("Surepass %s connection error: %s", tag, exc.reason)
        raise SurepassTimeout("Could not reach the verification service.") from None

    # Response body intentionally NOT logged — it contains PAN/Aadhaar PII.

    try:
        return status, json.loads(raw)
    except ValueError:
        raise SurepassError("Verification returned an unexpected response.") from None


def mask_pan(pan):
    p = (pan or "").upper().strip()
    return p[:2] + "X" * (len(p) - 4) + p[-2:] if len(p) >= 4 else "XXXX"


def mask_aadhaar(aadhaar):
    digits = "".join(c for c in (aadhaar or "") if c.isdigit())
    return "XXXX XXXX " + digits[-4:] if len(digits) >= 4 else "XXXX XXXX XXXX"


def names_match(a, b):
    """Loose name match: at least one shared token and >=50% token overlap of
    the shorter name. Good enough to flag a clearly-different PAN holder."""
    def toks(s):
        cleaned = "".join(c.lower() if (c.isalnum() or c.isspace()) else " " for c in (s or ""))
        return {t for t in cleaned.split() if len(t) > 1}
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return False
    shared = len(ta & tb)
    return shared >= 1 and shared >= min(len(ta), len(tb)) * 0.5


def pan_comprehensive(pan):
    """Look up a PAN. Returns {"name": str, "ref": str, "pan_masked": str}."""
    _status, body = _call_surepass(PAN_ENDPOINT, {"id_number": pan}, tag="kyc pan")
    data = (body or {}).get("data") or {}
    name = data.get("full_name") or data.get("name") or data.get("registered_name") or ""
    ref = data.get("client_id") or (body or {}).get("client_id") or ""
    return {"name": str(name).strip(), "ref": str(ref), "pan_masked": mask_pan(pan)}


def digilocker_initialize(redirect_url):
    """Start a Digilocker via-link session. Returns {"url": str, "client_id": str}.

    The seller is redirected to `url`; Surepass returns them to `redirect_url`.
    """
    payload = {"data": {
        "signup_flow": False,
        "redirect_url": redirect_url,
        "state": "carfriend_kyc",
        "skip_main_screen": False,
    }}
    _status, body = _call_surepass(DIGILOCKER_INIT_ENDPOINT, payload, tag="kyc digilocker init")
    data = (body or {}).get("data") or {}
    return {
        "url": data.get("url") or data.get("redirect_url") or "",
        "client_id": str(data.get("client_id") or ""),
    }


def digilocker_fetch_aadhaar(client_id):
    """Fetch the Aadhaar result after the Digilocker return.

    Returns {"name": str, "aadhaar_masked": str, "ref": str}. The raw Aadhaar
    number is NEVER stored — only the masked value is returned.
    """
    _status, body = _call_surepass(DIGILOCKER_AADHAAR_ENDPOINT, {"client_id": client_id}, tag="kyc digilocker aadhaar")
    data = (body or {}).get("data") or {}
    name = data.get("full_name") or data.get("name") or ""
    aadhaar = data.get("aadhaar_number") or data.get("aadhaar") or data.get("masked_aadhaar") or ""
    return {"name": str(name).strip(), "aadhaar_masked": mask_aadhaar(aadhaar), "ref": str(client_id)}


# ── Challan / traffic violations (Surepass) ──────────────────────────────────
# Reuses the same auth/client (_call_surepass, SUREPASS_TOKEN, SUREPASS_BASE).
# Surepass challan endpoint path + response field names must be confirmed from
# console.surepass.app; the parser below is defensive (tries the common field
# names). The raw response body is never logged (it may contain PII); only the
# status code is.
CHALLAN_ENDPOINT = "/api/v1/challan/challan"
CHALLAN_TIMEOUT = 15  # challan lookups are slower than RC


def _money(raw):
    """Best-effort numeric parse of an amount that may be '₹500', '500.00', 500."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    digits = "".join(c for c in str(raw) if c.isdigit() or c == ".")
    try:
        return float(digits) if digits else 0.0
    except ValueError:
        return 0.0


def _challan_date(raw):
    """Return an ISO date if parseable, else the original string (challans often
    carry a date+time stamp). Never raises."""
    s = (str(raw) if raw is not None else "").strip()
    if not s:
        return ""
    iso = _iso_date(s.split(" ")[0].split("T")[0])
    return iso or s


def _join_offences(offences):
    """Offences may be a list of dicts/strings or a plain string."""
    if not offences:
        return ""
    if isinstance(offences, str):
        return offences.strip()
    names = []
    for o in offences if isinstance(offences, (list, tuple)) else [offences]:
        if isinstance(o, dict):
            names.append(str(o.get("offense_name") or o.get("offence_name")
                             or o.get("name") or o.get("description") or "").strip())
        else:
            names.append(str(o).strip())
    return ", ".join(n for n in names if n)


def _normalize_challans(body):
    """Map a raw Surepass challan response → the normalized result structure."""
    data = (body or {}).get("data") or {}
    raw_list = (data.get("challans") or data.get("challan_details")
                or data.get("challan") or data.get("pending_challans") or [])
    if isinstance(raw_list, dict):
        raw_list = raw_list.get("challans") or raw_list.get("data") or []

    challans, total_pending = [], 0.0
    for c in raw_list or []:
        if not isinstance(c, dict):
            continue
        amount = _money(c.get("amount") or c.get("fine_amount")
                        or c.get("challan_amount") or c.get("penalty"))
        status_raw = str(c.get("challan_status") or c.get("status")
                         or c.get("payment_status") or "").strip().lower()
        is_paid = status_raw in ("paid", "disposed", "cash", "settled", "closed", "completed")
        offence = (c.get("offence_description") or c.get("offense_description")
                   or _join_offences(c.get("offenses") or c.get("offences"))
                   or c.get("offence") or c.get("offense") or c.get("violation") or "")
        challans.append({
            "challan_number": str(c.get("challan_number") or c.get("challan_no")
                                  or c.get("number") or "").strip(),
            "offense_date": _challan_date(c.get("challan_date") or c.get("offense_date")
                                          or c.get("date") or c.get("challan_date_time")),
            "amount": amount,
            "payment_status": "paid" if is_paid else "pending",
            "offence_description": str(offence).strip(),
            "location": str(c.get("location") or c.get("state")
                            or c.get("area") or c.get("rto") or "").strip(),
        })
        if not is_paid:
            total_pending += amount

    return {
        "status": "ok",
        "challans": challans,
        "total_challans": len(challans),
        "total_pending_amount": round(total_pending, 2),
        "has_pending": any(ch["payment_status"] == "pending" for ch in challans),
    }


def fetch_challans(rc_number, chassis="", engine=""):
    """Fetch traffic challans for a vehicle RC via Surepass. NEVER raises.

    Returns a normalized dict:
      {status: "ok"|"no_data"|"failed", challans: [...], total_challans: int,
       total_pending_amount: float, has_pending: bool}
    Each challan: {challan_number, offense_date, amount, payment_status,
                   offence_description, location}.
    """
    empty = {"status": "failed", "challans": [], "total_challans": 0,
             "total_pending_amount": 0.0, "has_pending": False}
    rc = (rc_number or "").strip().upper().replace(" ", "")
    if not rc:
        return empty

    payload = {"id_number": rc}
    # Some Surepass challan plans require the last 5 of chassis + engine.
    if chassis:
        payload["chassis"] = str(chassis).strip()[-5:]
    if engine:
        payload["engine"] = str(engine).strip()[-5:]

    try:
        _status, body = _call_surepass(CHALLAN_ENDPOINT, payload, tag="challan",
                                       method="POST", timeout=CHALLAN_TIMEOUT)
    except SurepassNotFound:
        return {**empty, "status": "no_data"}
    except SurepassError as exc:
        logger.warning("Challan lookup failed for rc=%s: %s", rc, exc)
        return {**empty, "status": "failed"}
    except Exception:
        logger.exception("Challan lookup crashed for rc=%s", rc)
        return {**empty, "status": "failed"}

    try:
        return _normalize_challans(body)
    except Exception:
        logger.exception("Challan normalize crashed for rc=%s", rc)
        return {**empty, "status": "failed"}


# ─────────────────────────────────────────────────────────────────────────────
# SurePass Aadhaar e-Sign  (a SEPARATE SurePass product from the KYC/RC/PAN calls
# above; reuses the same SUREPASS_TOKEN / SUREPASS_BASE_URL). Unlike _call_surepass,
# these return a STRUCTURED result and never raise — the caller must SURFACE the
# actual SurePass status/message (sandbox may answer "product not enabled"). There is
# NO fake-sign fallback: a party is signed only when SurePass returns completed.
# ─────────────────────────────────────────────────────────────────────────────

SUREPASS_ESIGN_INIT_PATH   = config("SUREPASS_ESIGN_INIT_PATH",   default="/api/v1/esign/initialize")
SUREPASS_ESIGN_STATUS_PATH = config("SUREPASS_ESIGN_STATUS_PATH", default="/api/v1/esign/get-status")


def _esign_raw(path, payload, method="POST"):
    """Low-level SurePass e-Sign call. Returns {ok, status, message, data} and NEVER
    raises, so the actual SurePass response can be surfaced to the user/logs."""
    token = config("SUREPASS_TOKEN", default="")
    if not token:
        return {"ok": False, "status": 0, "message": "SUREPASS_TOKEN is not set.", "data": {}}
    url = SUREPASS_BASE + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        logger.warning("Surepass e-Sign HTTP error: status=%s", status)
    except (socket.timeout, TimeoutError):
        return {"ok": False, "status": 0, "message": "SurePass e-Sign timed out.", "data": {}}
    except urllib.error.URLError as exc:
        return {"ok": False, "status": 0, "message": f"Could not reach SurePass e-Sign: {exc.reason}", "data": {}}
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        body = {}
    # SurePass envelopes vary: {success, message, message_code, data:{...}}.
    msg = (body.get("message") or body.get("message_code")
           or body.get("status_code") or f"HTTP {status}")
    ok = (200 <= int(status or 0) < 300) and (body.get("success") is not False)
    return {"ok": bool(ok), "status": int(status or 0), "message": str(msg), "data": body}


def esign_initialize(*, pdf_url, signer_name, signer_email, signer_phone, reference, callback_url):
    """Initiate an Aadhaar e-Sign for ONE party. Returns
    {ok, status, message, signing_url, client_id, data}. On success `signing_url` is the
    SurePass-hosted page to redirect the signer to; `client_id` is the transaction ref."""
    payload = {
        "pdf_url": pdf_url,
        "callback_url": callback_url,
        "config": {"auth_mode": "1", "reason": "Vehicle sale agreement",
                   "positions": {}, "allow_download": True},
        "prefill_options": {"full_name": signer_name or "",
                            "mobile_number": signer_phone or "",
                            "user_email": signer_email or ""},
        "reference_id": reference,
    }
    r = _esign_raw(SUREPASS_ESIGN_INIT_PATH, payload)
    d = r.get("data") or {}
    inner = d.get("data") if isinstance(d.get("data"), dict) else d
    r["signing_url"] = (inner.get("url") or inner.get("signed_url")
                        or inner.get("esign_url") or inner.get("redirect_url") or "")
    r["client_id"] = (inner.get("client_id") or inner.get("id")
                      or inner.get("reference_id") or "")
    return r


def esign_fetch_status(client_id):
    """Confirm a signing transaction with SurePass. Returns {ok, status, message,
    completed, signed_pdf_url, data}. `completed` is True only when SurePass reports the
    document as signed/completed — the sole gate for marking a party signed."""
    r = _esign_raw(SUREPASS_ESIGN_STATUS_PATH, {"client_id": client_id})
    d = r.get("data") or {}
    inner = d.get("data") if isinstance(d.get("data"), dict) else d
    state = str(inner.get("status") or inner.get("esign_status") or "").lower()
    completed = bool(inner.get("signed") or inner.get("completed")
                     or state in ("completed", "signed", "success", "esign_done"))
    r["completed"] = completed
    r["signed_pdf_url"] = inner.get("signed_pdf_url") or inner.get("pdf_url") or ""
    return r
