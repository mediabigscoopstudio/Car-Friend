import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class AuctionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.auction_id = self.scope["url_route"]["kwargs"]["auction_id"]
        self.group = f"auction_{self.auction_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send(json.dumps(await self.state()))

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (ValueError, TypeError):
            return
        if data.get("type") != "bid":
            return
        # SECURITY: the bidder is the AUTHENTICATED session user — never a
        # client-supplied dealer_id (which a dealer could spoof). Any dealer_id
        # in the message is ignored.
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.send(json.dumps({"type": "error", "msg": "Please log in to bid."}))
            return
        try:
            amount = int(data.get("amount"))
        except (TypeError, ValueError):
            await self.send(json.dumps({"type": "error", "msg": "Enter a valid bid amount."}))
            return
        ok, payload = await self.place_bid(user.id, amount)
        if ok:
            await self.channel_layer.group_send(
                self.group, {"type": "bid.broadcast", "payload": payload}
            )
        else:
            await self.send(json.dumps({"type": "error", "msg": payload}))

    async def bid_broadcast(self, event):
        await self.send(json.dumps({"type": "bid", **event["payload"]}))

    @database_sync_to_async
    def state(self):
        from .models import Auction

        a = Auction.objects.get(pk=self.auction_id)
        hb = a.highest_bid
        return {
            "type":     "state",
            "status":   a.status,
            "highest":  hb.amount if hb else a.reserve_price,
            "by_id":    hb.dealer_id if hb else None,
            "ends_at":  a.end_at.isoformat(),
            "count":    a.bids.count(),
        }

    @database_sync_to_async
    def place_bid(self, dealer_id, amount):
        import datetime
        from django.db import transaction
        from django.utils import timezone
        from .models import Auction, Bid

        from accounts.models import DealerVerification

        # Atomic — select_for_update needs a transaction, and it serialises
        # concurrent bids so the min-increment check can't be raced.
        with transaction.atomic():
            a = Auction.objects.select_for_update().get(pk=self.auction_id)
            if not a.is_live:
                return False, "Auction is not live."
            # Re-check server-side: only an APPROVED-verified dealer can bid.
            if not DealerVerification.objects.filter(
                dealer_id=dealer_id, status=DealerVerification.Status.APPROVED
            ).exists():
                return False, "Your dealer account is not verified yet. Complete verification to bid."
            hb = a.highest_bid
            floor = (hb.amount if hb else a.reserve_price) + a.min_increment
            if amount < floor:
                return False, f"Minimum next bid is ₹{floor:,}."
            bid = Bid.objects.create(auction=a, dealer_id=dealer_id, amount=amount)
            # Anti-snipe: a bid in the last minute extends the clock by 60s.
            if (a.end_at - timezone.now()).total_seconds() < 60:
                a.end_at += datetime.timedelta(seconds=60)
                a.save(update_fields=["end_at"])
            return True, {
                "highest":  amount,
                "by_id":    bid.dealer_id,    # never the username — client shows "You"/"Dealer"
                "ends_at":  a.end_at.isoformat(),
                "count":    a.bids.count(),
            }
