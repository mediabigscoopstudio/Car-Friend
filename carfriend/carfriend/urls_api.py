from django.http import JsonResponse
from django.urls import path

from auctions import api as aapi
from inspections import api as iapi

urlpatterns = [
    path("", lambda r: JsonResponse({"service": "Car Friend API", "status": "ok"})),
    path("inspections/<int:report_id>/checkpoint", iapi.checkpoint_autosave),
    path("inspections/<int:report_id>/media", iapi.media_upload),
    path("inspections/<int:report_id>/dent", iapi.dent_add),
    path("auctions/<int:auction_id>/state", aapi.auction_state),
]
