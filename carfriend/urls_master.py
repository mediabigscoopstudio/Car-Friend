from django.urls import include, path
from functools import partial

from core.views import coming_soon

urlpatterns = [
    path("", partial(coming_soon, host_label="Master"), name="home"),
    path("core/", include("core.urls")),
    path("kyc/", include("kyc.urls")),
    path("payments/", include("payments.urls")),
    path("notifications/", include("notifications.urls")),
]
