"""Car Friend price-estimate engine.

ALL tunable constants live in this module so pricing can be adjusted without
touching view/flow code. The formula is intentionally simple and transparent;
swap in a real valuation model later (see TODOs).

Public API:
    KM_BANDS                 -> ordered list of selectable kilometre bands
    band_midpoint(key)       -> assumed actual km for a band
    compute_estimate(...)    -> dict with low / high / value and the inputs used
"""

import datetime

# ── Tunables ────────────────────────────────────────────────────────────────

CURRENT_YEAR = datetime.date.today().year

FLOOR = 40_000          # estimates never go below this
DISPLAY_SPREAD_LOW = 0.94   # low  = value * 0.94, rounded to nearest 5000
DISPLAY_SPREAD_HIGH = 1.06  # high = value * 1.06, rounded to nearest 5000
DISPLAY_ROUND = 5_000       # round displayed band ends to nearest this

# condition_factor is a placeholder hook for a future inspection score (0–1+).
DEFAULT_CONDITION_FACTOR = 1.0

# Fraction of base (ex-showroom-when-new) price retained at a given age in years.
AGE_RETENTION = {
    0: 0.90, 1: 0.82, 2: 0.73, 3: 0.65, 4: 0.58, 5: 0.51,
    6: 0.45, 7: 0.40, 8: 0.35, 9: 0.31, 10: 0.27,
}


def age_retention(age):
    """Retention fraction for a given vehicle age (years)."""
    if age <= 10:
        return AGE_RETENTION[max(0, age)]
    # age > 10: keep falling 2 percentage points per year, but never below 0.10
    return max(0.27 - 0.02 * (age - 10), 0.10)


# ── Base prices (approximate ex-showroom-when-new, INR) ──────────────────────
# TODO: expand this table substantially and keep it fresh. Keys are normalised
# (see _norm) so matching is case/spacing-insensitive.
#
# Most specific match wins: (brand, model, variant) -> (brand, model) ->
# SEGMENT_DEFAULTS[segment] -> GLOBAL_DEFAULT.

BASE_PRICES_VARIANT = {
    # brand,        model,       variant   : price
    ("hyundai", "i20 n line", "n8"):        1_150_000,
    ("hyundai", "i20 n line", "n6"):        1_100_000,
}

BASE_PRICES_MODEL = {
    # brand,        model         : price
    ("hyundai", "i20 n line"):     1_100_000,   # << demo car family
    ("hyundai", "i20"):              800_000,
    ("hyundai", "creta"):          1_300_000,
    ("hyundai", "venue"):            900_000,
    ("hyundai", "verna"):          1_200_000,
    ("hyundai", "grand i10"):        650_000,
    ("maruti suzuki", "swift"):      750_000,
    ("maruti suzuki", "baleno"):     800_000,
    ("maruti suzuki", "dzire"):      800_000,
    ("maruti suzuki", "wagonr"):     600_000,
    ("maruti suzuki", "brezza"):   1_000_000,
    ("maruti suzuki", "ertiga"):   1_100_000,
    ("tata", "nexon"):             1_000_000,
    ("tata", "punch"):               750_000,
    ("tata", "tiago"):               650_000,
    ("tata", "harrier"):           1_700_000,
    ("tata", "altroz"):              750_000,
    ("mahindra", "scorpio n"):     1_600_000,
    ("mahindra", "scorpio"):       1_300_000,
    ("mahindra", "xuv700"):        2_000_000,
    ("mahindra", "thar"):          1_500_000,
    ("mahindra", "bolero"):          950_000,
    ("mahindra", "xuv300"):          950_000,
    ("honda", "city"):             1_300_000,
    ("honda", "amaze"):              800_000,
    ("honda", "jazz"):               850_000,
    ("toyota", "innova"):          2_000_000,
    ("toyota", "fortuner"):        3_500_000,
    ("toyota", "glanza"):            800_000,
    ("kia", "seltos"):             1_300_000,
    ("kia", "sonet"):              1_000_000,
    ("kia", "carens"):             1_300_000,
    ("renault", "kwid"):             550_000,
    ("renault", "triber"):           750_000,
}

# Fallback by rough body/price segment when the model is unknown.
SEGMENT_DEFAULTS = {
    "hatchback": 600_000,
    "sedan":     900_000,
    "suv":     1_200_000,
    "muv":     1_000_000,
}

GLOBAL_DEFAULT = 700_000   # last-resort base price


# ── Kilometre bands ──────────────────────────────────────────────────────────
# midpoint = assumed actual_km for the band. The open top band uses its lower
# bound * 1.1 per spec.

KM_BANDS = [
    {"key": "0_10k",    "label": "Up to 10,000 km",     "midpoint": 5_000},
    {"key": "10_20k",   "label": "10,000 – 20,000 km",  "midpoint": 15_000},
    {"key": "20_30k",   "label": "20,000 – 30,000 km",  "midpoint": 25_000},
    {"key": "30_40k",   "label": "30,000 – 40,000 km",  "midpoint": 35_000},
    {"key": "40_50k",   "label": "40,000 – 50,000 km",  "midpoint": 45_000},
    {"key": "50_70k",   "label": "50,000 – 70,000 km",  "midpoint": 60_000},
    {"key": "70_100k",  "label": "70,000 – 1,00,000 km", "midpoint": 85_000},
    {"key": "over_100k", "label": "Over 1,00,000 km",    "midpoint": int(100_000 * 1.1)},
]
_BAND_BY_KEY = {b["key"]: b for b in KM_BANDS}


def band_midpoint(key):
    band = _BAND_BY_KEY.get(key)
    return band["midpoint"] if band else None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _norm(s):
    return (s or "").strip().lower()


def lookup_base_price(brand, model, variant=None, segment=None):
    """Most-specific-match-wins base price lookup."""
    b, m, v = _norm(brand), _norm(model), _norm(variant)
    if v and (b, m, v) in BASE_PRICES_VARIANT:
        return BASE_PRICES_VARIANT[(b, m, v)]
    if (b, m) in BASE_PRICES_MODEL:
        return BASE_PRICES_MODEL[(b, m)]
    if segment and _norm(segment) in SEGMENT_DEFAULTS:
        return SEGMENT_DEFAULTS[_norm(segment)]
    return GLOBAL_DEFAULT


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _round_to(x, base=DISPLAY_ROUND):
    return int(base * round(float(x) / base))


def mileage_factor(age, actual_km):
    """Higher-than-expected usage lowers value, lower usage raises it."""
    expected_km = max(6_000, age * 11_000)
    ratio = actual_km / expected_km
    return _clamp(1 - (ratio - 1) * 0.12, 0.82, 1.08)


def compute_estimate(brand, model, variant, year, km_band_key,
                     segment=None, condition_factor=DEFAULT_CONDITION_FACTOR):
    """Return an estimate dict for the given car + selected kilometre band.

    Keys: low, high, value, base_price, age, retention, mileage_factor,
    condition_factor, actual_km, band_key.
    """
    try:
        year = int(year)
    except (TypeError, ValueError):
        year = CURRENT_YEAR

    age = max(0, CURRENT_YEAR - year)
    base_price = lookup_base_price(brand, model, variant, segment)

    actual_km = band_midpoint(km_band_key)
    if actual_km is None:
        actual_km = max(6_000, age * 11_000)  # neutral assumption if band missing

    retention = age_retention(age)
    mf = mileage_factor(age, actual_km)

    value = base_price * retention * mf * condition_factor
    value = max(value, FLOOR)

    low = _round_to(value * DISPLAY_SPREAD_LOW)
    high = _round_to(value * DISPLAY_SPREAD_HIGH)

    return {
        "low": low,
        "high": high,
        "value": int(round(value)),
        "base_price": base_price,
        "age": age,
        "retention": round(retention, 4),
        "mileage_factor": round(mf, 4),
        "condition_factor": condition_factor,
        "actual_km": actual_km,
        "band_key": km_band_key,
    }
