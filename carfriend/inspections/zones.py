# inspections/zones.py
# ---------------------------------------------------------------------------
# Walk-around inspection template (v4 brief §5.2 / §5.4 / §5.9).
#
# This replaces the system-based CHECKPOINT_SCHEMA *flow* with a physical
# walk-around an inspector actually performs. It is pure CONFIG (no UI): a
# versioned map of zones -> groups -> checkpoints -> part_type, plus the
# tailored problem-chip dictionary and the tunable scoring rules.
#
# Capture model (§5.3): every checkpoint defaults UNSET; the inspector resolves
# each as OK / Issue / N/A (kind="issue"), captures a value (kind="field"), or
# takes a required photo (kind="doc"). The engine treats a zone as done when
# every checkpoint is resolved.
#
# Nothing here is hardcoded into screens — adding a checkpoint or a chip never
# touches template code. Bump TEMPLATE_VERSION when the shape changes.
# ---------------------------------------------------------------------------

TEMPLATE_VERSION = 1

# Part types -> drive the tailored problem chips (§5.4). Keep keys stable.
PT_BODY      = "body_panel"
PT_GLASS     = "glass"
PT_MIRROR    = "mirror"
PT_LIGHT     = "light"
PT_TYRE      = "tyre"
PT_ALLOY     = "alloy"
PT_WIPER     = "wiper"
PT_SEAT      = "seat"
PT_DASH      = "dashboard"
PT_INFO      = "infotainment"
PT_WINDOW    = "power_window"
PT_AC        = "ac"
PT_WARN      = "warning_lights"
PT_ENGINE    = "engine_bay"
PT_BATTERY   = "battery"
PT_FLUIDS    = "fluids"
PT_BRAKES    = "brakes"
PT_STEER     = "steering_suspension"
PT_TRANS     = "transmission"
PT_EXHAUST   = "exhaust"
PT_DRIVE     = "testdrive"
PT_RC        = "rc_documents"
PT_INSURANCE = "insurance"
PT_KEYS      = "keys"

# §5.4 tailored problem-option dictionary, keyed by part_type. Multi-select.
PROBLEM_CHIPS = {
    PT_BODY:    ["Scratched", "Dented", "Repainted", "Rusted", "Paint faded",
                 "Panel gap / misaligned", "Cladding/molding damaged"],
    PT_GLASS:   ["Cracked", "Chipped", "Scratched", "Delaminated", "Sunfilm bubbling"],
    PT_MIRROR:  ["Cracked", "Fold/motor not working", "Auto-fold broken",
                 "Cover broken", "Indicator not working"],
    PT_LIGHT:   ["Not working", "Flickering", "Foggy/yellowed", "Cracked lens",
                 "Condensation inside"],
    PT_TYRE:    ["Worn (low tread)", "Cut / sidewall damage", "Bulge", "Uneven wear",
                 "Brand mismatch", "Cracked/aged", "Wrong size"],
    PT_ALLOY:   ["Curb rash / scratched", "Bent", "Corroded", "Aftermarket"],
    PT_WIPER:   ["Streaking/worn", "Not working", "Washer not spraying"],
    PT_SEAT:    ["Torn", "Stained", "Sagging", "Burn mark", "Worn bolster",
                 "Aftermarket covers"],
    PT_DASH:    ["Cracked", "Scratched", "Rattle", "Faded", "Sticky/peeling"],
    PT_INFO:    ["Not working", "Touch unresponsive", "Speaker issue", "Camera fault",
                 "Bluetooth/USB fault"],
    PT_WINDOW:  ["Slow", "Not working", "Auto up/down fault", "Switch broken"],
    PT_AC:      ["Weak cooling", "Not cooling", "Noisy blower", "Smell", "Vent broken",
                 "Heater fault"],
    PT_WARN:    ["Check-engine on", "ABS/airbag light", "Service due",
                 "Odometer-tamper suspicion", "Cluster fault"],
    PT_ENGINE:  ["Oil leak", "Coolant leak", "Low oil", "Contaminated oil",
                 "Belt cracked/worn", "Mount worn", "Excessive noise", "Smoke",
                 "Radiator damage", "Aftermarket wiring"],
    PT_BATTERY: ["Weak", "Leaking", "Corroded terminals", "Aftermarket", "Date expired"],
    PT_FLUIDS:  ["Low level", "Leak", "Weak/old", "Contaminated/discoloured"],
    PT_BRAKES:  ["Soft/spongy pedal", "Noise (squeal/grind)", "Pulls to side",
                 "Worn pads", "Low fluid", "Weak handbrake"],
    PT_STEER:   ["Pulls", "Vibration", "Hard/heavy", "Play in wheel", "Knock over bumps",
                 "Leaking shock", "Worn bush"],
    PT_TRANS:   ["Slipping", "Hard shift", "Grinding", "Jerks", "Noise in gear",
                 "Auto-box jerky"],
    PT_EXHAUST: ["Noise", "Smoke (blue/white/black)", "Rust/leak", "Modified"],
    PT_DRIVE:   ["Hard start", "Rough idle", "Stalling", "Hesitation", "Lack of power",
                 "Overheating", "Vibration at speed", "NVH/rattles"],
    PT_RC:      ["RC not available", "Damaged", "Name mismatch", "Hypothecation present",
                 "Duplicate RC", "Address mismatch", "HSRP/embossing missing"],
    PT_INSURANCE: ["Expired", "Not available", "Claim history", "Third-party only"],
    PT_KEYS:    ["Only one key", "No spare", "Fob not working", "Remote dead"],
}

# Severity (§5.5) — required on every Issue; weights the score.
SEVERITIES = [
    {"key": "minor",    "label": "Minor"},
    {"key": "moderate", "label": "Moderate"},
    {"key": "major",    "label": "Major"},
]

# §5.9 scoring — documented, tunable. Score starts at 100; each issue subtracts
# (severity penalty x part-type weight). Grade banded from the final score.
SEVERITY_PENALTY = {"minor": 2, "moderate": 5, "major": 11}
PART_WEIGHT = {           # structural / drivetrain faults hurt more than cosmetic
    PT_ENGINE: 1.6, PT_TRANS: 1.6, PT_BRAKES: 1.5, PT_STEER: 1.4, PT_FLUIDS: 1.3,
    PT_BATTERY: 1.2, PT_DRIVE: 1.4, PT_WARN: 1.3, PT_RC: 1.5, PT_INSURANCE: 1.2,
    PT_TYRE: 1.2, PT_GLASS: 1.1, PT_AC: 1.0, PT_LIGHT: 1.0, PT_BODY: 1.0,
}
GRADE_BANDS = [(85, "A"), (70, "B"), (50, "C"), (0, "D")]


def _cp(key, label, pt, kind="issue", photo="opt", na=False):
    return {"key": key, "label": label, "pt": pt, "kind": kind, "photo": photo, "na": na}


def _side(prefix, label_prefix, pt, kind="issue"):
    """LHS/RHS front+rear helper for doors/tyres/alloys etc. handled inline."""
    return _cp(prefix, label_prefix, pt, kind)


# ---------------------------------------------------------------------------
# The zone map. Order == the inspector's walk around the car (§5.2).
# ---------------------------------------------------------------------------
ZONES = [
    {
        "key": "details", "index": 0, "title": "Car Details & registry", "short": "Details",
        "groups": [
            {"label": "Identity (verify from RC)", "checkpoints": [
                _cp("reg_number", "Registration number", PT_RC, kind="field"),
                _cp("owner_name", "Owner name", PT_RC, kind="field"),
                _cp("make_model", "Make & model", PT_RC, kind="field"),
                _cp("variant_transmission", "Variant + transmission (confirm)", PT_RC, kind="field"),
                _cp("mfg_month_year", "Mfg month/year & reg date", PT_RC, kind="field"),
                _cp("fuel_owners", "Fuel type · no. of owners", PT_RC, kind="field"),
            ]},
            {"label": "Physical capture", "checkpoints": [
                _cp("odometer_km", "Odometer / KM reading", PT_WARN, kind="field", photo="req"),
                _cp("rc_card", "RC card — availability, condition, name match", PT_RC, photo="req"),
                _cp("keys_spare", "Keys / spare key", PT_KEYS, photo="req"),
                _cp("hsrp_embossing", "HSRP / chassis embossing present", PT_RC),
                _cp("service_history", "Service history available", PT_RC, kind="field", photo="opt", na=True),
            ]},
        ],
    },
    {
        "key": "left", "index": 1, "title": "Left side", "short": "Left",
        "groups": [
            {"label": "Panels", "checkpoints": [
                _cp("l_fender_front", "Front-left fender", PT_BODY),
                _cp("l_door_front", "Front-left door", PT_BODY),
                _cp("l_door_rear", "Rear-left door", PT_BODY),
                _cp("l_quarter", "Rear-left quarter panel", PT_BODY),
                _cp("l_pillar_a", "A-pillar (left)", PT_BODY),
                _cp("l_pillar_b", "B-pillar (left)", PT_BODY),
                _cp("l_pillar_c", "C-pillar (left)", PT_BODY),
                _cp("l_running_board", "Running board / cladding (left)", PT_BODY),
            ]},
            {"label": "Mirror & wheels", "checkpoints": [
                _cp("l_orvm", "Left ORVM", PT_MIRROR),
                _cp("l_tyre_front", "Front-left tyre", PT_TYRE, photo="opt"),
                _cp("l_tyre_rear", "Rear-left tyre", PT_TYRE, photo="opt"),
                _cp("l_alloy_front", "Front-left alloy", PT_ALLOY),
                _cp("l_alloy_rear", "Rear-left alloy", PT_ALLOY),
            ]},
        ],
    },
    {
        "key": "front", "index": 2, "title": "Front & engine bay", "short": "Front",
        "groups": [
            {"label": "Front exterior", "checkpoints": [
                _cp("bonnet", "Bonnet", PT_BODY),
                _cp("front_bumper", "Front bumper", PT_BODY),
                _cp("grille", "Grille", PT_BODY),
                _cp("headlamp_l", "Headlamp (left)", PT_LIGHT),
                _cp("headlamp_r", "Headlamp (right)", PT_LIGHT),
                _cp("foglamp_l", "Fog lamp (left)", PT_LIGHT, na=True),
                _cp("foglamp_r", "Fog lamp (right)", PT_LIGHT, na=True),
                _cp("windshield_front", "Windshield", PT_GLASS),
                _cp("wipers_front", "Front wipers + washer", PT_WIPER),
                _cp("number_plate_front", "Front number plate", PT_BODY),
            ]},
            {"label": "Front structure", "checkpoints": [
                _cp("apron", "Apron", PT_BODY),
                _cp("firewall", "Firewall", PT_BODY),
                _cp("cowl_top", "Cowl top", PT_BODY),
                _cp("lower_cross_member", "Lower cross member", PT_BODY),
                _cp("upper_cross_member", "Upper cross member (bonnet patti)", PT_BODY),
                _cp("headlight_support", "Head light support", PT_BODY),
                _cp("radiator_support", "Radiator support", PT_BODY),
            ]},
            {"label": "Engine bay (bonnet open)", "checkpoints": [
                _cp("engine_condition", "Engine condition", PT_ENGINE, photo="opt"),
                _cp("engine_oil_level", "Engine oil level (dipstick)", PT_FLUIDS),
                _cp("engine_oil_condition", "Engine oil condition", PT_FLUIDS),
                _cp("coolant", "Coolant level/condition", PT_FLUIDS),
                _cp("radiator", "Radiator", PT_ENGINE),
                _cp("battery", "Battery — brand/date/terminals", PT_BATTERY),
                _cp("belts", "Belts", PT_ENGINE),
                _cp("engine_mounts", "Engine mounts", PT_ENGINE),
                _cp("visible_leaks", "Visible leaks", PT_ENGINE),
                _cp("fluid_reservoirs", "Fluid reservoirs", PT_FLUIDS),
                _cp("wiring", "Wiring", PT_ENGINE),
                _cp("turbo_charger", "Turbo charger", PT_ENGINE, na=True),
                _cp("fuel_injector", "Fuel injector", PT_ENGINE, na=True),
            ]},
        ],
    },
    {
        "key": "right", "index": 3, "title": "Right side", "short": "Right",
        "groups": [
            {"label": "Mirror & panels", "checkpoints": [
                _cp("r_orvm", "Right ORVM", PT_MIRROR),
                _cp("r_door_front", "Front-right door", PT_BODY),
                _cp("r_door_rear", "Rear-right door", PT_BODY),
                _cp("r_fender_front", "Front-right fender", PT_BODY),
                _cp("r_quarter", "Rear-right quarter panel", PT_BODY),
                _cp("r_pillar_a", "A-pillar (right)", PT_BODY),
                _cp("r_pillar_b", "B-pillar (right)", PT_BODY),
                _cp("r_pillar_c", "C-pillar (right)", PT_BODY),
                _cp("r_running_board", "Running board / cladding (right)", PT_BODY),
            ]},
            {"label": "Wheels", "checkpoints": [
                _cp("r_tyre_front", "Front-right tyre", PT_TYRE, photo="opt"),
                _cp("r_tyre_rear", "Rear-right tyre", PT_TYRE, photo="opt"),
                _cp("r_alloy_front", "Front-right alloy", PT_ALLOY),
                _cp("r_alloy_rear", "Rear-right alloy", PT_ALLOY),
            ]},
        ],
    },
    {
        "key": "rear", "index": 4, "title": "Rear", "short": "Rear",
        "groups": [
            {"label": "Rear exterior", "checkpoints": [
                _cp("boot_door", "Boot / dickey door", PT_BODY),
                _cp("boot_floor", "Boot floor, hinges, seal", PT_BODY),
                _cp("rear_bumper", "Rear bumper", PT_BODY),
                _cp("taillight_l", "Tail light (left)", PT_LIGHT),
                _cp("taillight_r", "Tail light (right)", PT_LIGHT),
                _cp("rear_windshield", "Rear windshield", PT_GLASS),
                _cp("number_plate_rear", "Rear number plate", PT_BODY),
            ]},
            {"label": "Spare & exhaust", "checkpoints": [
                _cp("spare_tyre", "Spare tyre", PT_TYRE, na=True),
                _cp("tools_jack", "Tools / jack", PT_KEYS, kind="field", na=True),
                _cp("exhaust_tip", "Exhaust tip", PT_EXHAUST),
            ]},
        ],
    },
    {
        "key": "inside", "index": 5, "title": "Inside (cabin + test drive)", "short": "Inside",
        "groups": [
            {"label": "Cabin", "checkpoints": [
                _cp("power_windows_count", "No. of power windows", PT_WINDOW, kind="field", na=True),
                _cp("airbags_count", "No. of airbags", PT_WARN, kind="field", na=True),
                _cp("seats_upholstery", "Seats / upholstery", PT_SEAT),
                _cp("dashboard_trim", "Dashboard / trim", PT_DASH),
                _cp("steering_wheel", "Steering wheel", PT_STEER),
                _cp("infotainment", "Infotainment / music system", PT_INFO),
                _cp("reverse_camera", "Reverse camera", PT_INFO, na=True),
                _cp("ac_climate", "AC / climate control", PT_AC),
                _cp("power_windows", "Power windows", PT_WINDOW),
                _cp("central_locking", "Central locking", PT_WINDOW),
                _cp("electricals_cabin", "All electricals", PT_INFO),
                _cp("warning_lights", "Odometer / warning lights", PT_WARN),
                _cp("roof_headliner", "Roof / headliner", PT_SEAT),
                _cp("pedals", "Pedals", PT_BRAKES),
                _cp("sunroof", "Sunroof", PT_INFO, na=True),
                _cp("airbags", "Airbags present & light OK", PT_WARN),
                _cp("rear_defogger", "Rear defogger", PT_INFO, na=True),
                _cp("abs_feature", "ABS", PT_BRAKES, na=True),
            ]},
        ],
    },
    {
        # Structured Test Drive section (drivability + live 1KM GPS drive +
        # suspension/brake) — rendered from InspectionReport fields, NOT
        # checkpoints. Auction only (hidden for scrap via engine.zones_for).
        "key": "testdrive", "index": 6, "title": "Test drive", "short": "Test drive",
        "groups": [],
    },
    {
        "key": "docs", "index": 7, "title": "Documents & wrap-up", "short": "Docs",
        "groups": [
            {"label": "Documents", "checkpoints": [
                _cp("doc_rc", "RC photo", PT_RC, kind="doc", photo="req"),
                _cp("doc_insurance", "Insurance photo", PT_INSURANCE, kind="doc", photo="req"),
                _cp("doc_service", "Service records photo", PT_RC, kind="doc", photo="opt", na=True),
                _cp("doc_duplicate_key", "Duplicate-key photo", PT_KEYS, kind="doc", photo="opt", na=True),
            ]},
            # The old "360° set & sign-off" group is replaced by the WRAP-UP block
            # (front/rear/left/right photos + walk-around video + engine audio +
            # final notes), rendered from InspectionReport model fields in the
            # docs zone template — not as checkpoints.
        ],
    },
]

ZONE_BY_KEY = {z["key"]: z for z in ZONES}
ZONE_ORDER = [z["key"] for z in ZONES]


def zone_checkpoints(zone):
    for g in zone["groups"]:
        for cp in g["checkpoints"]:
            yield cp


def all_checkpoints():
    for z in ZONES:
        for cp in zone_checkpoints(z):
            yield z["key"], cp


def checkpoint_count(zone):
    return sum(len(g["checkpoints"]) for g in zone["groups"])


def chips_for(part_type):
    return PROBLEM_CHIPS.get(part_type, [])


def grade_for(score):
    for cutoff, letter in GRADE_BANDS:
        if score >= cutoff:
            return letter
    return "D"
