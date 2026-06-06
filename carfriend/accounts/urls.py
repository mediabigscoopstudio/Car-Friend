from django.urls import path
from accounts import views

urlpatterns = [
    path("login/",            views.login_page,        name="login"),
    path("register/",         views.register_page,     name="register"),
    path("logout/",           views.logout_page,       name="logout"),
    path("role-redirect/",    views.role_redirect,     name="role_redirect"),
    path("set-role/",         views.set_role,          name="set_role"),
    path("seller/dashboard/", views.seller_dashboard,  name="seller_dashboard"),
    path("dealer/dashboard/", views.dealer_dashboard,  name="dealer_dashboard"),
]
