"""Routes for the mobile-app (/app/*) surface. Mounted under 'app/' in urls_public.py.

Additive only — a separate module from www/urls.py so the existing public site is untouched.
"""

from django.urls import path

from www import app_views

urlpatterns = [
    path("", app_views.app_router, name="app_home"),            # /app/  (role-aware router / welcome)
    path("login/", app_views.app_login, name="app_login"),      # /app/login/
    path("register/", app_views.app_register, name="app_register"),  # /app/register/
    path("seller/", app_views.app_seller_home, name="app_seller_home"),  # /app/seller/
    path("dealer/", app_views.app_dealer_home, name="app_dealer_home"),  # /app/dealer/
]
