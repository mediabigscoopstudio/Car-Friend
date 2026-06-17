import re

from django import template
register = template.Library()

_ACRONYMS = {"cng", "lpg", "rc", "rto", "noc", "abs", "orvm", "lhs", "rhs", "ac", "km"}

# Corporate-suffix noise to drop from a raw vehicle name (e.g. "India Ltd").
_CORP_STOPWORDS = {"india", "ltd", "ltd.", "limited", "pvt", "pvt.", "private"}
# Maruti-style variant tokens (vxi, lxi, zxi, vdi, ldi, zdi…) → "VXi", "LDi".
_VARIANT_RE = re.compile(r"^[a-z]{2,3}i$")


@register.filter
def dictkey(d, key):
    if not isinstance(d, dict):
        return ""
    return d.get(key, "")


@register.filter
def cellfor(checkpoints, args):
    """Usage: checkpoints|cellfor:'section:part_key:subpart'"""
    try:
        section, part_key, subpart = args.split(":")
        return checkpoints.get(section, {}).get(part_key, {}).get(subpart, {})
    except Exception:
        return {}


@register.filter
def short_car_name(vehicle):
    """Tidy a raw vehicle name for display.

    Drops corporate noise ("India Ltd"), de-duplicates repeated words
    (e.g. "Maruti … Maruti", "Vxi Vxi"), and applies sensible casing.
    "Maruti Suzuki India Ltd Maruti Dzire Vxi Vxi" → "Maruti Suzuki Dzire VXi".
    """
    raw = getattr(vehicle, "display_name", None) or str(vehicle or "")
    out, seen = [], set()
    for word in raw.split():
        low = word.lower()
        if low in _CORP_STOPWORDS or low in seen:
            continue
        seen.add(low)
        if low in _ACRONYMS:
            out.append(word.upper())
        elif _VARIANT_RE.match(low):
            out.append(low[:-1].upper() + "i")
        else:
            out.append(word.title())
    return " ".join(out)


@register.filter
def humanize(value):
    """Convert snake_case field key → 'Title Case' respecting common acronyms."""
    words = str(value).replace("_", " ").split()
    return " ".join(w.upper() if w.lower() in _ACRONYMS else w.title() for w in words)
