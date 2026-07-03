"""Car Friend margin / grossing engine — the single source of money math.

THE INVARIANT: every price a DEALER sees, bids, or pays is GROSS (base + margin
+ GST). Every price a SELLER sees or is paid is BASE. `gross_breakdown()` goes
base -> gross (the canonical direction). `base_from_gross()` inverts a
dealer-facing gross price back to the seller's base (regime-aware) so
seller-facing views can display the number in the seller's own terms.

ALL money math in the project goes through this module — no inline grossing
anywhere else. (www/pricing.py is depreciation/valuation only and is unrelated.)

Config lives in settings (env-overridable); this module falls back to the spec
defaults if Django settings are unavailable (e.g. a standalone unit test):
    CF_GST_PERCENT     = 18     # GST %, applied to the MARGIN only
    CF_MARGIN_PERCENT  = 7      # margin %
    CF_MARGIN_FLOOR    = 10000  # minimum margin, rupees
    CF_RC_HOLD         = 5000   # separate RC-transfer amount (NOT part of gross)

Every returned rupee value is a whole rupee (Decimal quantised ROUND_HALF_UP,
never negative).
"""
from decimal import Decimal, ROUND_HALF_UP

_DEFAULTS = {
    "CF_GST_PERCENT": 18,
    "CF_MARGIN_PERCENT": 7,
    "CF_MARGIN_FLOOR": 10000,
    "CF_RC_HOLD": 5000,
}


def _cfg(name):
    """Read a CF_* setting, falling back to the spec default when Django settings
    are unavailable or the value is unset (keeps the module unit-testable)."""
    try:
        from django.conf import settings
        return getattr(settings, name)
    except Exception:
        return _DEFAULTS[name]


def _D(x):
    return x if isinstance(x, Decimal) else Decimal(str(x))


def _rupees(x):
    """Whole rupees, ROUND_HALF_UP, clamped to >= 0."""
    v = _D(x).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(v) if v > 0 else 0


def _factors():
    m = _D(_cfg("CF_MARGIN_PERCENT")) / Decimal(100)   # 0.07
    g = _D(_cfg("CF_GST_PERCENT")) / Decimal(100)       # 0.18
    floor = _D(_cfg("CF_MARGIN_FLOOR"))                 # 10000
    return m, g, floor


def gross_breakdown(base):
    """base -> {base, margin, gst, gross}.

    margin = max(m*base, floor); gst = g*margin (GST on the MARGIN only);
    gross = base + margin + gst.
    """
    m, g, floor = _factors()
    base = _D(base)
    if base < 0:
        base = Decimal(0)
    margin = max(m * base, floor)
    gst = g * margin
    gross = base + margin + gst
    return {"base": _rupees(base), "margin": _rupees(margin),
            "gst": _rupees(gst), "gross": _rupees(gross)}


def base_from_gross(gross):
    """gross -> {base, margin, gst, gross} (regime-aware inverse).

    Above the floor boundary the 7% regime holds, so base = gross / k where
    k = 1 + m*(1+g). Below it the flat floor margin applies, so
    base = gross - floor*(1+g). The split is then recomputed forward from the
    resolved base so the returned {margin, gst, gross} are self-consistent.
    """
    m, g, floor = _factors()
    gross = _D(gross)
    if gross < 0:
        gross = Decimal(0)
    k = Decimal(1) + m * (Decimal(1) + g)      # 7%-regime multiplier (1.0826)
    boundary = floor / m                        # base at which m*base == floor
    base_pct = gross / k
    if base_pct >= boundary:
        base = base_pct                         # 7% regime
    else:
        base = gross - floor * (Decimal(1) + g)  # floor regime (gross - 11800)
    if base < 0:
        base = Decimal(0)
    return gross_breakdown(base)


def rc_hold():
    """The separate RC-transfer amount a dealer pays on top of the car gross."""
    return _rupees(_cfg("CF_RC_HOLD"))


def inverse_params():
    """Constants for a client-side de-gross (e.g. the seller's live WS ticker),
    so browser JS uses the SAME numbers as base_from_gross() — no divergent money
    logic. Returns floats: k (regime multiplier), boundary, floor_gst = floor*(1+g).
    """
    m, g, floor = _factors()
    k = Decimal(1) + m * (Decimal(1) + g)
    boundary = floor / m
    floor_gst = floor * (Decimal(1) + g)
    return {"k": float(k), "boundary": float(boundary), "floor_gst": float(floor_gst)}
