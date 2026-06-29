from django.utils import timezone

from auctions.models import Auction


def auto_close_expired_auctions():
    """Flip live auctions whose end_at has passed to 'closed' so the seller's
    post-auction decision flow can pick them up.

    Status-only update (matches the manual admin close in views.auction_pause) —
    the OCB / CRM pipeline acts on the closed auction afterwards. Bulk .update()
    so it is cheap to call on every dashboard load and fires no model signals.
    Returns the number of auctions closed.
    """
    return (Auction.objects
            .filter(status=Auction.Status.LIVE, end_at__lte=timezone.now())
            .update(status=Auction.Status.CLOSED, updated_at=timezone.now()))
