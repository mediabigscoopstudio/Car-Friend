from django.urls import path
from accounts import views

urlpatterns = [
    path("login/",            views.login_page,        name="login"),
    path("register/",         views.register_page,     name="register"),
    path("logout/",           views.logout_page,       name="logout"),
    path("role-redirect/",    views.role_redirect,     name="role_redirect"),
    path("choose-role/",      views.choose_role,       name="choose_role"),
    path("set-role/",         views.set_role,          name="set_role"),
    path("login/dealer/",     views.login_as_dealer,   name="login_as_dealer"),
    path("login/seller/",     views.login_as_seller,   name="login_as_seller"),
    path("seller/dashboard/", views.seller_dashboard,   name="seller_dashboard"),
    path("dealer/dashboard/", views.dealer_dashboard,   name="dealer_dashboard"),
    path("dealer/onboard/",   views.dealer_onboard,    name="dealer_onboard"),
    path("switch-role/",      views.switch_role,       name="switch_role"),
]
