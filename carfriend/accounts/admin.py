from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, SellerProfile, DealerProfile


@admin.register(User)
class CFUserAdmin(UserAdmin):
    list_display  = ("username", "email", "role", "is_internal", "is_suspended", "created_at")
    list_filter   = ("role", "is_internal", "is_suspended")
    fieldsets     = UserAdmin.fieldsets + (
        ("Car Friend", {"fields": ("role", "phone", "is_internal", "is_suspended", "fcm_token")}),
    )


admin.site.register(SellerProfile)
admin.site.register(DealerProfile)
