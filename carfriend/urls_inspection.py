from django.urls import include, path
from functools import partial

from core.views import coming_soon

urlpatterns = [
    path("", partial(coming_soon, host_label="Inspection"), name="home"),
    path("inspections/", include("inspections.urls")),
]
