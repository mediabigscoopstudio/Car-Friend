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
        data = json.loads(text_data)
        if data.get("type") == "bid":
            ok, payload = await self.place_bid(data["dealer_id"], int(data["amount"]))
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
            "by":       hb.dealer.username if hb else None,
            "ends_at":  a.end_at.isoformat(),
            "count":    a.bids.count(),
        }

    @database_sync_to_async
    def place_bid(self, dealer_id, amount):
        import datetime
        from django.utils import timezone
        from .models import Auction, Bid

        from accounts.models import DealerVerification

        a = Auction.objects.select_for_update().get(pk=self.auction_id)
        if not a.is_live:
            return False, "Auction is not live."
        # A dealer can bid only with an APPROVED verification.
        if not DealerVerification.objects.filter(
            dealer_id=dealer_id, status=DealerVerification.Status.APPROVED
        ).exists():
            return False, "Your dealer account is not verified yet. Complete verification to bid."
        hb = a.highest_bid
        floor = (hb.amount if hb else a.reserve_price) + a.min_increment
        if amount < floor:
            return False, f"Minimum next bid is ₹{floor:,}."
        bid = Bid.objects.create(auction=a, dealer_id=dealer_id, amount=amount)
        if (a.end_at - timezone.now()).total_seconds() < 60:
            a.end_at += datetime.timedelta(seconds=60)
            a.save(update_fields=["end_at"])
        return True, {
            "highest":  amount,
            "by":       bid.dealer.username,
            "ends_at":  a.end_at.isoformat(),
            "count":    a.bids.count(),
        }
