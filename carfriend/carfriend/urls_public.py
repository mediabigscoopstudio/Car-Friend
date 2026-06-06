from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    # allauth — Google OAuth + built-in account management
    path("accounts/", include("allauth.urls")),
    # CarFriend auth — login, register, dashboards
    path("auth/", include("accounts.urls")),
    # Public website
    path("", include("www.urls")),
    # Sub-app public URLs
    path("vehicles/", include("vehicles.urls")),
    path("auctions/", include("auctions.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
