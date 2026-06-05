from django import template
register = template.Library()

_ACRONYMS = {"cng", "lpg", "rc", "rto", "noc", "abs", "orvm", "lhs", "rhs", "ac", "km"}


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
def humanize(value):
    """Convert snake_case field key → 'Title Case' respecting common acronyms."""
    words = str(value).replace("_", " ").split()
    return " ".join(w.upper() if w.lower() in _ACRONYMS else w.title() for w in words)
