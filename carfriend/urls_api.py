from django.http import JsonResponse
from django.urls import path

urlpatterns = [
    path("", lambda r: JsonResponse({"service": "Car Friend API", "status": "ok"})),
]
