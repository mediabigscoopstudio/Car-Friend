from django.urls import path

from . import views

app_name = "kyc"
urlpatterns = [path("", views.index, name="index")]
