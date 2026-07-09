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
AADHAAR_RE = re.compile(r"^[0-9]{12}$")
MOBILE_RE = re.compile(r"^[0-9]{10}$")

PATH_FORMAL = "formal"
PATH_SMALL = "small"
PATH_CHOICES = [
    (PATH_FORMAL, "I have GSTIN (Path 1)"),
    (PATH_SMALL, "I have Udyam + Gumasta (Path 2)"),
]


class DealerVerificationForm(forms.Form):
    """Two-path dealer verification. The compulsory CORE is always required; the chosen
    PATH's number fields are enforced in clean(). Documents are validated separately in
    the view via validate_document + required_docs_for_path (files aren't form fields)."""
    # Compulsory core
    business_name   = forms.CharField(max_length=200)
    city            = forms.CharField(max_length=120)
    official_mobile = forms.CharField(max_length=15)
    official_email  = forms.EmailField()
    aadhaar_number  = forms.CharField(max_length=12)
    path            = forms.ChoiceField(choices=PATH_CHOICES)
    # Path 1 (formal) numbers — optional at field level, enforced per path in clean().
    gstin      = forms.CharField(max_length=20, required=False)
    pan_number = forms.CharField(max_length=20, required=False)
    tan_number = forms.CharField(max_length=40, required=False)
    aoa_number = forms.CharField(max_length=40, required=False)

    def clean_business_name(self):
        v = (self.cleaned_data.get("business_name") or "").strip()
        if not v:
            raise forms.ValidationError("Legal business name is required.")
        return v

    def clean_city(self):
        v = (self.cleaned_data.get("city") or "").strip()
        if not v:
            raise forms.ValidationError("City is required.")
        return v

    def clean_official_mobile(self):
        v = (self.cleaned_data.get("official_mobile") or "").strip()
        if not MOBILE_RE.match(v):
            raise forms.ValidationError("Enter a valid 10-digit official mobile number.")
        return v

    def clean_aadhaar_number(self):
        v = "".join(c for c in (self.cleaned_data.get("aadhaar_number") or "") if c.isdigit())
        if not AADHAAR_RE.match(v):
            raise forms.ValidationError("Enter a valid 12-digit Aadhaar number.")
        return v

    def clean_gstin(self):
        # Validated only when non-empty; per-path requirement is enforced in clean().
        v = (self.cleaned_data.get("gstin") or "").strip().upper()
        if v and not GSTIN_RE.match(v):
            raise forms.ValidationError("Enter a valid 15-character GSTIN (e.g. 22AAAAA0000A1Z5).")
        return v

    def clean(self):
        cleaned = super().clean()
        path = cleaned.get("path")
        if path == PATH_FORMAL:
            for f, label in (("gstin", "GSTIN"), ("pan_number", "PAN"),
                             ("tan_number", "TAN"), ("aoa_number", "AOA")):
                if not (cleaned.get(f) or "").strip():
                    self.add_error(f, f"{label} is required for Path 1 (formal business).")
        elif path != PATH_SMALL:
            self.add_error("path", "Choose how you register your business.")
        return cleaned


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
