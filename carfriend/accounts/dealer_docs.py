"""Required documents for dealer verification.

Easily extensible: add or remove (key, label) tuples here and the onboarding
form, the per-document records, and the admin detail view all follow. Keep keys
stable (they are stored on DealerDocument.doc_type).
"""

DEALER_REQUIRED_DOCS = [
    ("gst_certificate", "GST Certificate"),
    ("pan_card",        "PAN Card"),
    ("tan_card",        "TAN Card"),
    ("aoa",             "Articles of Association (AOA)"),
]

DEALER_DOC_LABELS = dict(DEALER_REQUIRED_DOCS)

# Upload validation
ALLOWED_DOC_EXTS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_DOC_CONTENT_TYPES = {"application/pdf", "image/jpeg", "image/png"}
MAX_DOC_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
