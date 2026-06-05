from django.urls import include, path
from functools import partial

from core.views import coming_soon

urlpatterns = [
    path("", partial(coming_soon, host_label=""), name="home"),
    path("accounts/", include("accounts.urls")),
    path("vehicles/", include("vehicles.urls")),
    path("auctions/", include("auctions.urls")),
]
