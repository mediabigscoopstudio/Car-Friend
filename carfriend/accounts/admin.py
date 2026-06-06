from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, SellerProfile, DealerProfile, Role


@admin.register(User)
class CFUserAdmin(UserAdmin):
    list_display  = ("email", "first_name", "last_name", "role", "is_kyc_done", "is_approved", "is_internal", "is_suspended", "created_at")
    list_filter   = ("role", "is_kyc_done", "is_approved", "is_internal", "is_suspended", "is_active")
    search_fields = ("email", "first_name", "last_name", "phone")
    ordering      = ("-created_at",)
    fieldsets     = UserAdmin.fieldsets + (
        ("CarFriend Profile", {
            "fields": ("role", "phone", "city", "is_internal", "is_suspended", "is_kyc_done", "is_approved", "fcm_token")
        }),
    )


admin.site.register(SellerProfile)
admin.site.register(DealerProfile)
