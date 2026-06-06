from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="home"),
    path("how-it-works/", views.how_it_works, name="how_it_works"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("cookies/", views.cookies, name="cookies"),
    path("auction-rules/", views.auction_rules, name="auction_rules"),
    path("seller-agreement/", views.seller_agreement, name="seller_agreement"),
    path("refund-policy/", views.refund_policy, name="refund_policy"),
    path("kyc-policy/", views.kyc_policy, name="kyc_policy"),
    path("inspection-policy/", views.inspection_policy, name="inspection_policy"),
    path("grievance/", views.grievance, name="grievance"),
]
