from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from accounts import views as a
from auctions import views as au
from core import views as c
from crm import views_master as crm
from inspections import views as ins
from kyc import views as k
from payments import views as p

urlpatterns = [
    path("", c.master_dashboard, name="master_dashboard"),
    path("login_view", a.login_view, name="login_view"),
    path("logout_view", a.logout_view, name="logout_view"),
    # user management
    path("users", a.users, name="users"),
    path("add_user", a.add_user, name="add_user"),
    path("suspend_user/<int:id>", a.suspend_user, name="suspend_user"),
    # inspection oversight
    path("inspection_queue", ins.inspection_queue, name="inspection_queue"),
    path("inspection_review/<int:id>", ins.inspection_review, name="inspection_review"),
    path("inspection_decide/<int:id>", ins.inspection_decide, name="inspection_decide"),
    # KYC
    path("kyc_queue", k.kyc_queue, name="kyc_queue"),
    path("kyc_decide/<int:id>", k.kyc_decide, name="kyc_decide"),
    # Dealer verification approvals (super admin)
    path("dealer_verifications", a.dealer_verifications, name="dealer_verifications"),
    path("dealer_verifications/<int:id>/", a.dealer_verification_detail, name="dealer_verification_detail"),
    path("dealer_verifications/<int:id>/decide", a.dealer_verification_decide, name="dealer_verification_decide"),
    path("dealer_document/<int:doc_id>/", a.dealer_document_download, name="dealer_document_download"),
    # payments
    path("payments_pending", p.payments_pending, name="payments_pending"),
    path("payment_confirm/<int:id>", p.payment_confirm, name="payment_confirm"),
    # auctions
    path("auction/<int:id>", au.auction_room, name="auction_room"),
    path("auctions_overview", au.auctions_overview, name="auctions_overview"),
    path("auction_reactivate/<int:id>", au.auction_reactivate, name="auction_reactivate"),
    path("auction_pause/<int:id>", au.auction_pause, name="auction_pause"),
    path("bid_void/<int:id>", au.bid_void, name="bid_void"),
    # Retail CRM — lead pipeline + sellers
    path("pipeline",                                    crm.master_pipeline,          name="master_pipeline"),
    path("pipeline/<int:lead_id>/",                     crm.master_lead_detail,       name="master_lead_detail"),
    path("pipeline/<int:lead_id>/move/",                crm.master_lead_move,         name="master_lead_move"),
    path("pipeline/<int:lead_id>/assign-inspector/",    crm.master_assign_inspector,  name="master_assign_inspector"),
    path("pipeline/<int:lead_id>/note/",                crm.master_lead_add_note,     name="master_lead_add_note"),
    path("sellers",                                     crm.master_sellers,           name="sellers"),
    # Sales CRM — dealer network + deals
    path("dealers",                                     crm.master_dealers,           name="dealers"),
    path("dealers/<int:dealer_id>/",                    crm.master_dealer_detail,     name="master_dealer_detail"),
    path("deals",                                       crm.master_deals,             name="deals"),
    path("deals/<int:vehicle_id>/",                     crm.master_deal_detail,       name="master_deal_detail"),
    # Inspector overview
    path("inspector",                                   crm.master_inspector_dashboard, name="master_inspector_dashboard"),
    # platform
    path("features", c.feature_toggles, name="features"),
    path("audit", c.audit_log_view, name="audit"),
    path("leads", au.lead_hub, name="leads"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
