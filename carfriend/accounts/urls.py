from django.urls import path
from accounts import views
from accounts import otp_views

urlpatterns = [
    # Phone-OTP auth for the mobile apps (NEW, additive — the existing routes below are untouched).
    path("otp/request/", otp_views.otp_request, name="otp_request"),
    path("otp/verify/",  otp_views.otp_verify,  name="otp_verify"),
    path("login/",            views.login_page,        name="login"),
    path("register/",         views.register_page,     name="register"),
    path("logout/",           views.logout_page,       name="logout"),
    path("role-redirect/",    views.role_redirect,     name="role_redirect"),
    path("set-role/",         views.set_role,          name="set_role"),
    path("login/dealer/",     views.login_as_dealer,   name="login_as_dealer"),
    path("login/seller/",     views.login_as_seller,   name="login_as_seller"),
    path("seller/dashboard/", views.seller_dashboard,   name="seller_dashboard"),
    path("dealer/dashboard/", views.dealer_dashboard,   name="dealer_dashboard"),
    path("dealer/onboard/",   views.dealer_onboard,    name="dealer_onboard"),
    path("switch-role/",      views.switch_role,       name="switch_role"),
    # Seller profile / account
    path("profile/",               views.profile,               name="profile"),
    path("profile/edit/",          views.profile_edit,          name="profile_edit"),
    path("profile/payout/",        views.profile_payout,        name="profile_payout"),
    path("profile/notifications/", views.profile_notifications, name="profile_notifications"),
]
