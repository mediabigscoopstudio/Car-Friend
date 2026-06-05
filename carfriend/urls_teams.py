from django.urls import include, path
from functools import partial

from core.views import coming_soon

urlpatterns = [
    path("", partial(coming_soon, host_label="Teams"), name="home"),
    path("crm/", include("crm.urls")),
    path("deals/", include("deals.urls")),
]
