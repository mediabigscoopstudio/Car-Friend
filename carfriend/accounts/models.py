from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ADMIN     = "admin",     "Admin"
    RETAIL    = "retail",    "Retail Associate"
    SALES     = "sales",     "Sales Associate"
    INSPECTOR = "inspector", "Inspector"
    SELLER    = "seller",    "Seller"
    DEALER    = "dealer",    "Dealer/Buyer"


class User(AbstractUser):
    # Class-level constants for use in views
    ROLE_SELLER    = Role.SELLER
    ROLE_DEALER    = Role.DEALER
    ROLE_RETAIL    = Role.RETAIL
    ROLE_SALES     = Role.SALES
    ROLE_INSPECTOR = Role.INSPECTOR
    ROLE_ADMIN     = Role.ADMIN

    role         = models.CharField(max_length=20, choices=Role.choices, default=Role.SELLER)
    phone        = models.CharField(max_length=15, blank=True)
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

    def is_staff_role(self):
        return self.role in [Role.RETAIL, Role.SALES, Role.INSPECTOR, Role.ADMIN]


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

    def __str__(self): return self.dealership_name
