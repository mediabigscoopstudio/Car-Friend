from django.urls import path

from . import views_dealer as d
from . import views_winner as w

# Registered on the PUBLIC/www host (urls_public includes this at "auctions/"),
# so dealers reach the auction list at /auctions/ and a room at /auctions/<id>/.
urlpatterns = [
    path("", d.dealer_auction_list, name="dealer_auction_list"),
    path("ocb/offers/", w.winner_ocb_list, name="winner_ocb_list"),
    path("ocb/<int:listing_id>/respond/", w.winner_respond_view, name="winner_respond"),
    path("<int:id>/", d.dealer_auction_room, name="dealer_auction_room"),
]
