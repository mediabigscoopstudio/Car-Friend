from django.urls import include, path

urlpatterns = [
    path("", include("www.urls")),
    path("accounts/", include("accounts.urls")),
    path("vehicles/", include("vehicles.urls")),
    path("auctions/", include("auctions.urls")),
]
