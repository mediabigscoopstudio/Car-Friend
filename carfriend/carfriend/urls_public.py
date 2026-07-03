from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("admin/", admin.site.urls),  # alias — admin reachable at /admin/ and /django-admin/
    # allauth — Google OAuth + built-in account management
    path("accounts/", include("allauth.urls")),
    # CarFriend auth — login, register, dashboards
    path("auth/", include("accounts.urls")),
    # Public website
    path("", include("www.urls")),
    # Sub-app public URLs
    path("vehicles/", include("vehicles.urls")),
    path("auctions/", include("auctions.urls")),
    path("deals/", include("deals.urls")),
    # Seller KYC (PAN + Aadhaar)
    path("kyc/", include("kyc.urls")),
    # Seller/dealer account surfaces
    path("support/", include("support.urls")),
    path("notifications/", include("notifications.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
