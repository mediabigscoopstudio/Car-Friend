"""Required documents for dealer verification (two-path model).

Path 1 (formal business) uploads GST/PAN/TAN/AOA; Path 2 (small business) uploads
Gumasta + Udyam. Documents are stored as `DealerDocument` rows keyed by `doc_type`
(these keys) — keep keys stable. `DEALER_REQUIRED_DOCS` is the full choice set for
`DealerDocument.doc_type`; the per-path required set comes from `required_docs_for_path`.
"""

# Path 1 — formal business (GSTIN-registered).
PATH1_DOCS = [
    ("gst_certificate", "GST Certificate"),
    ("pan_card",        "PAN Card"),
    ("tan_card",        "TAN Card"),
    ("aoa",             "Articles of Association (AOA)"),
]

# Path 2 — small business (Udyam + Gumasta).
PATH2_DOCS = [
    ("gumasta", "Gumasta Dhara / Shop Act licence"),
    ("udyam",   "Udyam Certificate"),
]

# Full set = every possible doc_type (choices for DealerDocument.doc_type).
DEALER_REQUIRED_DOCS = PATH1_DOCS + PATH2_DOCS
DEALER_DOC_LABELS = dict(DEALER_REQUIRED_DOCS)


def required_docs_for_path(path):
    """The [(key, label), ...] a dealer must upload for the chosen path."""
    if path == "formal":
        return PATH1_DOCS
    if path == "small":
        return PATH2_DOCS
    return []


# Upload validation
ALLOWED_DOC_EXTS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_DOC_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_DOC_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
