from django.urls import path

from . import views
from . import views_dealer as d
from . import views_winner as w

# Registered on the PUBLIC/www host (urls_public includes this at "auctions/"),
# so dealers reach the auction list at /auctions/ and a room at /auctions/<id>/.
urlpatterns = [
    path("", d.dealer_auction_list, name="dealer_auction_list"),
    path("purchases/", d.dealer_purchases, name="dealer_purchases"),
    path("ocb/offers/", w.winner_ocb_list, name="winner_ocb_list"),
    path("ocb/<int:listing_id>/respond/", w.winner_respond_view, name="winner_respond"),
    path("ocb/<int:listing_id>/", w.winner_ocb_detail, name="winner_ocb_detail"),
    # Seller watch page — declared before the dealer-room catch-all so it matches.
    path("<int:auction_id>/seller/", views.seller_auction_watch, name="seller_auction_watch"),
    path("<int:auction_id>/decision/", views.seller_decision, name="seller_decision"),
    path("<int:auction_id>/result/", views.seller_auction_result, name="seller_auction_result"),
    path("<int:auction_id>/ocb/", views.seller_ocb, name="seller_ocb"),
    path("<int:id>/", d.dealer_auction_room, name="dealer_auction_room"),
]
