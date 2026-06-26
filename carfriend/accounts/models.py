from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.files.storage import FileSystemStorage
from django.db import models

from accounts.dealer_docs import DEALER_DOC_LABELS, DEALER_REQUIRED_DOCS

# Sensitive dealer documents live OUTSIDE MEDIA_ROOT (base_url=None) so they are
# never served by the public /media/ static handler. They are streamed only by
# the admin-only download view. A callable keeps migrations portable (serialized
# as a dotted path, not a baked-in absolute location).
def protected_storage():
    return FileSystemStorage(
        location=str(settings.BASE_DIR / "protected_media"),
        base_url=None,
    )


class Role(models.TextChoices):
    ADMIN        = "admin",        "Admin"
    LEAD_MANAGER = "lead_manager", "Lead Manager"
    RETAIL_HEAD  = "retail_head",  "Retail Head"
    SALES_HEAD   = "sales_head",   "Sales Head"
    RETAIL       = "retail",       "Retail Associate"
    SALES        = "sales",        "Sales Associate"
    INSPECTOR    = "inspector",    "Inspection Associate"
    PROCUREMENT  = "procurement",  "Procurement Associate"
    SELLER       = "seller",       "Seller"
    DEALER       = "dealer",       "Dealer/Buyer"


class User(AbstractUser):
    # Class-level constants for use in views
    ROLE_SELLER       = Role.SELLER
    ROLE_DEALER       = Role.DEALER
    ROLE_RETAIL       = Role.RETAIL
    ROLE_SALES        = Role.SALES
    ROLE_INSPECTOR    = Role.INSPECTOR
    ROLE_ADMIN        = Role.ADMIN
    ROLE_LEAD_MANAGER = Role.LEAD_MANAGER
    ROLE_PROCUREMENT  = Role.PROCUREMENT
    ROLE_RETAIL_HEAD  = Role.RETAIL_HEAD
    ROLE_SALES_HEAD   = Role.SALES_HEAD

    role         = models.CharField(max_length=20, choices=Role.choices, default=Role.SELLER)
    phone        = models.CharField(max_length=15, blank=True)
    # Phone-keyed guest accounts created from the public sell flow after OTP.
    phone_verified = models.BooleanField(default=False)
    is_guest       = models.BooleanField(default=False)
    city         = models.CharField(max_length=120, blank=True)
    is_internal  = models.BooleanField(default=False)
    is_suspended = models.BooleanField(default=False)
    is_kyc_done  = models.BooleanField(default=False)
    is_approved  = models.BooleanField(default=False)
    fcm_token    = models.CharField(max_length=255, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_full_name() or self.username} · {self.get_role_display()}"

    @property
    def is_admin(self):     return self.role == Role.ADMIN
    @property
    def is_retail(self):    return self.role == Role.RETAIL
    @property
    def is_sales(self):     return self.role == Role.SALES
    @property
    def is_inspector(self): return self.role == Role.INSPECTOR
    @property
    def is_seller(self):    return self.role == Role.SELLER
    @property
    def is_dealer(self):    return self.role == Role.DEALER
    @property
    def is_lead_manager(self): return self.role == Role.LEAD_MANAGER
    @property
    def is_procurement(self):  return self.role == Role.PROCUREMENT
    @property
    def is_retail_head(self):  return self.role == Role.RETAIL_HEAD
    @property
    def is_sales_head(self):   return self.role == Role.SALES_HEAD

    def is_staff_role(self):
        return self.role in [
            Role.ADMIN, Role.LEAD_MANAGER, Role.RETAIL_HEAD, Role.SALES_HEAD,
            Role.RETAIL, Role.SALES, Role.INSPECTOR, Role.PROCUREMENT,
        ]


class SellerProfile(models.Model):
    user       = models.OneToOneField(User, on_delete=models.CASCADE, related_name="seller_profile")
    city       = models.CharField(max_length=120, blank=True)
    address    = models.TextField(blank=True)
    kyc_done   = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self): return f"Seller · {self.user}"


class DealerProfile(models.Model):
    user            = models.OneToOneField(User, on_delete=models.CASCADE, related_name="dealer_profile")
    dealership_name = models.CharField(max_length=200)
    gstin           = models.CharField(max_length=20, blank=True)
    city            = models.CharField(max_length=120, blank=True)
    budget_min      = models.PositiveIntegerField(default=0)
    budget_max      = models.PositiveIntegerField(default=0)
    brand_interest  = models.CharField(max_length=255, blank=True)
    preferences     = models.TextField(blank=True)
    is_banned       = models.BooleanField(default=False)
    status          = models.CharField(max_length=20, default="Enabled")
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    @property
    def is_verified(self):
        return not self.is_banned and self.status == 'Enabled'

    def __str__(self): return self.dealership_name


class DealerVerification(models.Model):
    """A manual dealer verification submission, reviewed by a super admin.

    A dealer can bid only once they have an APPROVED verification.
    """

    class Status(models.TextChoices):
        PENDING  = "pending",  "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    dealer        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                      related_name="dealer_verifications")
    business_name = models.CharField(max_length=200)
    gstin         = models.CharField(max_length=20)
    status        = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    reject_reason = models.TextField(blank=True)
    submitted_at  = models.DateTimeField(auto_now_add=True)
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    reviewed_by   = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name="dealer_reviews")

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.business_name} · {self.get_status_display()}"

    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED


class DealerDocument(models.Model):
    """A single uploaded document for a dealer verification (kept private)."""

    DOC_CHOICES = DEALER_REQUIRED_DOCS

    verification = models.ForeignKey(DealerVerification, on_delete=models.CASCADE,
                                     related_name="documents")
    doc_type     = models.CharField(max_length=40, choices=DOC_CHOICES)
    file         = models.FileField(storage=protected_storage, upload_to="dealer_docs/")
    uploaded_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["doc_type"]

    @property
    def label(self):
        return DEALER_DOC_LABELS.get(self.doc_type, self.doc_type)

    def __str__(self):
        return f"{self.label} · {self.verification.business_name}"


def dealer_can_bid(user):
    """True only if the dealer has an APPROVED verification."""
    if not user or not user.is_authenticated:
        return False
    return DealerVerification.objects.filter(
        dealer=user, status=DealerVerification.Status.APPROVED
    ).exists()


def latest_dealer_verification(user):
    return DealerVerification.objects.filter(dealer=user).order_by("-submitted_at").first()
