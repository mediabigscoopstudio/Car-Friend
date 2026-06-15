from django.urls import path

from kyc import views_public as v

urlpatterns = [
    path("", v.kyc_page, name="kyc_page"),
    path("pan/", v.pan_verify, name="kyc_pan_verify"),
    path("aadhaar/start/", v.aadhaar_start, name="kyc_aadhaar_start"),
    path("aadhaar/callback/", v.aadhaar_callback, name="kyc_aadhaar_callback"),
]
