from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Auction


@api_view(["GET"])
def auction_state(request, auction_id):
    a = Auction.objects.get(pk=auction_id)
    hb = a.highest_bid
    return Response({
        "status":  a.status,
        "highest": hb.amount if hb else a.reserve_price,
        "ends_at": a.end_at,
        "count":   a.bids.count(),
    })
