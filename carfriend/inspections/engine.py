# inspections/engine.py
# ---------------------------------------------------------------------------
# Walk-around inspection ENGINE (logic only — no Django views/UI).
#
# Reads/writes checkpoint results inside InspectionReport.checkpoints JSON,
# namespaced under the "walk" key so it never clobbers the legacy section-based
# data that already lives at the top level. Computes per-zone + overall
# progress, the locked/active/done gating state, and the tunable score/grade.
#
# Decision (this build): extend the existing JSON model rather than add
# relational CheckpointResult tables. Photos still live in CheckpointPhoto /
# InspectionMedia rows; here we only track which photo ids back a checkpoint.
# ---------------------------------------------------------------------------

from .zones import (
    ZONES, ZONE_BY_KEY, ZONE_ORDER, zone_checkpoints, checkpoint_count,
    all_checkpoints, SEVERITY_PENALTY, PART_WEIGHT, grade_for, TEMPLATE_VERSION,
    PT_BODY,
)

WALK_KEY = "walk"


# ---- low-level store -------------------------------------------------------
def _walk(report):
    data = report.checkpoints or {}
    walk = data.get(WALK_KEY)
    if walk is None:
        walk = {"_v": TEMPLATE_VERSION, "results": {}}
        data[WALK_KEY] = walk
        report.checkpoints = data
    walk.setdefault("results", {})
    return walk


def results(report):
    return _walk(report).get("results", {})


def entry_for(report, key):
    return results(report).get(key)


def is_walk_inspection(report):
    """True once any walk-around result has been recorded (new flow)."""
    return bool((report.checkpoints or {}).get(WALK_KEY, {}).get("results"))


# ---- writing ---------------------------------------------------------------
def save_checkpoint(report, key, *, result=None, value=None, severity=None,
                    tags=None, note=None, voice=None, photos=None, ts=None,
                    crid=None, commit=True):
    """Upsert one checkpoint result. Only provided fields are written.

    Idempotent on `crid` (client_request_id): replaying the same request id is a
    no-op, so offline retries with backoff never double-apply (§5.11)."""
    walk = _walk(report)
    entry = walk["results"].get(key, {})
    if crid and entry.get("crid") == crid:
        return entry            # already applied this exact request
    if result is not None:   entry["result"] = result
    if value is not None:    entry["value"] = value
    if severity is not None: entry["severity"] = severity
    if tags is not None:     entry["tags"] = tags
    if note is not None:     entry["note"] = note
    if voice is not None:    entry["voice"] = voice
    if photos is not None:   entry["photos"] = photos
    if ts is not None:       entry["ts"] = ts
    if crid is not None:     entry["crid"] = crid
    # An OK / N/A result clears any stale issue metadata.
    if result in ("ok", "na"):
        entry.pop("severity", None)
        entry.pop("tags", None)
    walk["results"][key] = entry
    report.checkpoints[WALK_KEY] = walk
    if commit:
        report.save(update_fields=["checkpoints", "updated_at"])
    return entry


def mark_zone_good(report, zone_key, commit=True):
    """Bulk 'Mark all good' (§5.3): set every UNSET issue-kind checkpoint in the
    zone to OK. Already-resolved rows (incl. Issues) are left untouched."""
    zone = ZONE_BY_KEY[zone_key]
    walk = _walk(report)
    changed = 0
    for cp in visible_checkpoints(report, zone):     # scrap → never touches hidden engine rows
        if cp["kind"] != "issue":
            continue
        entry = walk["results"].get(cp["key"])
        if entry and entry.get("result"):
            continue
        walk["results"][cp["key"]] = {"result": "ok", "bulk": True}
        changed += 1
    report.checkpoints[WALK_KEY] = walk
    if commit:
        report.save(update_fields=["checkpoints", "updated_at"])
    return changed


# ---- resolution / progress -------------------------------------------------
def is_resolved(cp, entry):
    if not entry:
        return False
    if entry.get("result") == "na":
        return True
    kind = cp["kind"]
    if kind == "issue":
        return entry.get("result") in ("ok", "issue")
    if kind == "field":
        return bool(entry.get("value")) or bool(entry.get("photos"))
    if kind == "doc":
        return bool(entry.get("photos"))
    return bool(entry.get("result"))


# ── SCRAP checkpoint-level filtering ────────────────────────────────────────
# Scrap captures body/panel/frame condition + RC registry only. Everything else
# (physical-capture, insurance, engine, tyres/alloys, glass, lights, mirrors,
# interior/test-drive, doc photos) is stripped so ZERO engine info can appear.
_SCRAP_DETAILS_KEEP = "Identity (verify from RC)"     # the RC-registration group
_SCRAP_BODY_ZONES = {"left", "front", "right", "rear"}


def _is_scrap(report):
    return getattr(report, "disposition", "") == "scrap"


def scrap_group_visible(zone_key, group):
    """Whole-group visibility under scrap."""
    if zone_key == "details":
        return group["label"] == _SCRAP_DETAILS_KEEP   # RC registry only
    if zone_key == "docs":
        return False                                   # doc photos handled by wrap-up block
    return True


def scrap_cp_visible(zone_key, group, cp):
    """Checkpoint visibility under scrap: RC-identity in details; body/frame
    (PT_BODY) only in the exterior zones; nothing mechanical anywhere."""
    if not scrap_group_visible(zone_key, group):
        return False
    if zone_key in _SCRAP_BODY_ZONES:
        return cp.get("pt") == PT_BODY
    return True


def visible_groups(report, zone):
    """[(group, [checkpoints])] visible for this report's disposition.
    AUCTION/unset → every group + checkpoint (unchanged)."""
    scrap = _is_scrap(report)
    out = []
    for g in zone["groups"]:
        if scrap and not scrap_group_visible(zone["key"], g):
            continue
        cps = [cp for cp in g["checkpoints"]
               if not scrap or scrap_cp_visible(zone["key"], g, cp)]
        if cps:
            out.append((g, cps))
    return out


def visible_checkpoints(report, zone):
    for _g, cps in visible_groups(report, zone):
        for cp in cps:
            yield cp


def visible_keys(report):
    """Set of checkpoint keys the inspector may fill for this report's disposition."""
    return {cp["key"] for z in zones_for(report) for cp in visible_checkpoints(report, z)}


def zone_progress(report, zone):
    res = results(report)
    cps = list(visible_checkpoints(report, zone))
    total = len(cps)
    done = sum(1 for cp in cps if is_resolved(cp, res.get(cp["key"])))
    return {
        "resolved": done, "total": total,
        "pct": round(done * 100 / total) if total else 0,
        # A zone with no visible checkpoints (e.g. scrap 'docs') counts complete;
        # its wrap-up is gated separately at submit.
        "complete": done >= total,
        "issues": sum(1 for cp in cps
                      if (res.get(cp["key"]) or {}).get("result") == "issue"),
    }


SCRAP_HIDDEN_ZONES = {"inside", "testdrive"}   # cabin + test drive — not analysed for scrap


def zones_for(report):
    """Zones visible for this report's disposition. SCRAP → body-frame + paperwork
    only (hide cabin/test-drive). AUCTION or unset → the full walk (unchanged)."""
    if getattr(report, "disposition", "") == "scrap":
        return [z for z in ZONES if z["key"] not in SCRAP_HIDDEN_ZONES]
    return list(ZONES)


def overall_progress(report):
    res = results(report)
    total = done = 0
    zones_done = 0
    visible = zones_for(report)
    for z in visible:
        zp = zone_progress(report, z)
        total += zp["total"]; done += zp["resolved"]
        if zp["complete"]:
            zones_done += 1
    return {
        "checkpoints_done": done, "checkpoints_total": total,
        "pct": round(done * 100 / total) if total else 0,
        "zones_done": zones_done, "zones_total": len(visible),
        "issues": sum(1 for _k, cp in all_checkpoints()
                      if (res.get(cp["key"]) or {}).get("result") == "issue"),
    }


def active_zone_key(report):
    """First not-yet-complete VISIBLE zone in walk order, or None when all done."""
    for z in zones_for(report):
        if not zone_progress(report, z)["complete"]:
            return z["key"]
    return None


def zone_states(report):
    """locked / active / done per visible zone, for the gated ZoneCard list (§5.6).
    Position-based over the visible list so it is correct for both the full
    (auction) walk and the reduced (scrap) walk."""
    active = active_zone_key(report)
    out = []
    seen_active = False
    for z in zones_for(report):
        zp = zone_progress(report, z)
        if active is None:
            state = "done"
        elif z["key"] == active:
            state = "active"; seen_active = True
        elif not seen_active:
            state = "done"
        else:
            state = "locked"
        out.append({"zone": z, "state": state, "progress": zp})
    return out


def can_enter(report, zone_key):
    """Enterable only if the zone is VISIBLE for this disposition AND is the
    active one or already done."""
    states = {s["zone"]["key"]: s["state"] for s in zone_states(report)}
    return states.get(zone_key) in ("active", "done")


# ---- scoring (§5.9) --------------------------------------------------------
def compute_score(report):
    res = results(report)
    penalty = 0.0
    issues = []
    for _zk, cp in all_checkpoints():
        entry = res.get(cp["key"])
        if not entry or entry.get("result") != "issue":
            continue
        sev = entry.get("severity") or "moderate"
        base = SEVERITY_PENALTY.get(sev, SEVERITY_PENALTY["moderate"])
        weight = PART_WEIGHT.get(cp["pt"], 1.0)
        penalty += base * weight
        issues.append({"key": cp["key"], "label": cp["label"], "pt": cp["pt"],
                       "severity": sev, "tags": entry.get("tags", []),
                       "note": entry.get("note", "")})
    score = max(0, min(100, round(100 - penalty)))
    return {"score": score, "grade": grade_for(score), "issues": issues,
            "issue_count": len(issues)}


# market-value band by grade (§5.9) — tunable
GRADE_VALUE_FACTOR = {"A": 1.0, "B": 0.92, "C": 0.82, "D": 0.70}


def estimated_value(grade, base_price):
    try:
        base = float(base_price or 0)
    except (TypeError, ValueError):
        base = 0
    return int(round(base * GRADE_VALUE_FACTOR.get(grade, 0.85)))


def report_context(report, media_by_key=None):
    """Render-ready data for the walk-around report (inspector view, admin
    review, and PDF). media_by_key maps checkpoint key -> list of photo dicts."""
    media_by_key = media_by_key or {}
    res = results(report)
    sc = compute_score(report)
    ok = na = issue = 0
    zones_out = []
    for z in ZONES:
        groups = []
        z_issue = 0
        for g in z["groups"]:
            rows = []
            for cp in g["checkpoints"]:
                e = res.get(cp["key"]) or {}
                r_ = e.get("result")
                if r_ == "ok":
                    ok += 1
                elif r_ == "na":
                    na += 1
                elif r_ == "issue":
                    issue += 1; z_issue += 1
                rows.append({
                    "label": cp["label"], "kind": cp["kind"], "pt": cp["pt"],
                    "result": r_, "value": e.get("value", ""),
                    "severity": e.get("severity", ""), "tags": e.get("tags", []),
                    "note": e.get("note", ""), "photos": media_by_key.get(cp["key"], []),
                })
            groups.append({"label": g["label"], "rows": rows})
        zones_out.append({"key": z["key"], "title": z["title"],
                          "groups": groups, "issues": z_issue})
    return {
        "zones": zones_out, "score": sc["score"], "grade": sc["grade"],
        "issues": sc["issues"], "issue_count": sc["issue_count"],
        "ok": ok, "na": na, "issue_total": issue, "progress": overall_progress(report),
    }
