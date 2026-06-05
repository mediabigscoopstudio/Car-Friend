from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from accounts import views as a
from auctions import views as au
from core import views as c
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
    # payments
    path("payments_pending", p.payments_pending, name="payments_pending"),
    path("payment_confirm/<int:id>", p.payment_confirm, name="payment_confirm"),
    # auctions
    path("auctions_overview", au.auctions_overview, name="auctions_overview"),
    path("auction_reactivate/<int:id>", au.auction_reactivate, name="auction_reactivate"),
    path("auction_pause/<int:id>", au.auction_pause, name="auction_pause"),
    path("bid_void/<int:id>", au.bid_void, name="bid_void"),
    # platform
    path("features", c.feature_toggles, name="features"),
    path("audit", c.audit_log_view, name="audit"),
    path("leads", au.lead_hub, name="leads"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
