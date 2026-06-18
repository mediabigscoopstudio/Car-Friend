from django.urls import path

from . import views_dealer as d

# Registered on the PUBLIC/www host (urls_public includes this at "auctions/"),
# so dealers reach the auction list at /auctions/ and a room at /auctions/<id>/.
urlpatterns = [
    path("", d.dealer_auction_list, name="dealer_auction_list"),
    path("<int:id>/", d.dealer_auction_room, name="dealer_auction_room"),
]
