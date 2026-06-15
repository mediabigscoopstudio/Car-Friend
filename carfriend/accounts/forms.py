import os
import re

from django import forms

from accounts.dealer_docs import (
    ALLOWED_DOC_CONTENT_TYPES,
    ALLOWED_DOC_EXTS,
    MAX_DOC_SIZE_BYTES,
)

# Standard 15-char GSTIN: 2-digit state, 10-char PAN, entity digit, 'Z', checksum.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")


class DealerVerificationForm(forms.Form):
    business_name = forms.CharField(max_length=200)
    gstin = forms.CharField(max_length=20)

    def clean_business_name(self):
        v = (self.cleaned_data.get("business_name") or "").strip()
        if not v:
            raise forms.ValidationError("Legal business name is required.")
        return v

    def clean_gstin(self):
        v = (self.cleaned_data.get("gstin") or "").strip().upper()
        if not GSTIN_RE.match(v):
            raise forms.ValidationError("Enter a valid 15-character GSTIN (e.g. 22AAAAA0000A1Z5).")
        return v


def validate_document(upload):
    """Return an error string if the uploaded file is invalid, else None."""
    if not upload:
        return "File is required."
    ext = os.path.splitext(upload.name)[1].lower()
    if ext not in ALLOWED_DOC_EXTS:
        return "Only PDF, JPG or PNG files are allowed."
    if upload.size > MAX_DOC_SIZE_BYTES:
        return "Each file must be 5 MB or smaller."
    ctype = getattr(upload, "content_type", "") or ""
    if ctype and ctype not in ALLOWED_DOC_CONTENT_TYPES:
        return "Unsupported file type."
    return None
