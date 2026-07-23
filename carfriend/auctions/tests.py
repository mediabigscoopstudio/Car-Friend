import datetime

from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import path as urlpath
from django.utils import timezone

from accounts.models import DealerVerification, Role
from vehicles.models import Vehicle

from .consumers import AuctionConsumer
from .models import Auction, AutoBid, Bid

User = get_user_model()


def _mk_dealer(username):
    u = User.objects.create(username=username, role=Role.DEALER)
    DealerVerification.objects.create(
        dealer=u, business_name=f"{username} biz",
        status=DealerVerification.Status.APPROVED,
    )
    return u


def _mk_auction(reserve, min_increment, highest_seed=None):
    seller = User.objects.create(username=f"seller_{reserve}_{min_increment}", role=Role.SELLER)
    v = Vehicle.objects.create(
        seller=seller, plate_number=f"KA01ZZ{reserve % 100000}",
        make="Honda", model="City", year=2020,
        fuel_type=Vehicle.FUEL_PETROL, transmission=Vehicle.TRANSMISSION_MANUAL,
        colour="White",
    )
    now = timezone.now()
    auction = Auction.objects.create(
        vehicle=v, reserve_price=reserve, min_increment=min_increment,
        start_at=now, end_at=now + datetime.timedelta(minutes=30),
        status=Auction.Status.LIVE,
    )
    if highest_seed is not None:
        seed_dealer = _mk_dealer(f"seed_{reserve}_{min_increment}")
        Bid.objects.create(auction=auction, dealer=seed_dealer, amount=highest_seed)
    return auction


def _connect(auction, dealer):
    """A WebsocketCommunicator wired against the SAME URL pattern as carfriend/asgi.py
    (so self.scope['url_route']['kwargs']['auction_id'] resolves exactly as in production),
    with the authenticated user injected directly into scope — bypassing AuthMiddlewareStack/
    session cookies, which is the standard Channels testing pattern for consumers that read
    self.scope['user']."""
    router = URLRouter([urlpath("ws/auction/<auction_id>/", AuctionConsumer.as_asgi())])
    communicator = WebsocketCommunicator(router, f"/ws/auction/{auction.id}/")
    communicator.scope["user"] = dealer
    return communicator


class AutoBidCascadeTests(TransactionTestCase):
    """Regression coverage for the post-deploy report: (1) a bid from one dealer must reach
    every OTHER connected dealer's live WebSocket without a refresh, and (2) an active
    auto-bid ceiling must re-engage on a LATER competing bid from someone else, not just at
    the moment the ceiling was first set. Both go through the real AuctionConsumer — not a
    bypass — via two simultaneously connected sockets, matching how two dealer browser tabs
    actually behave.
    """

    async def test_competing_bid_broadcasts_live_and_retriggers_ceiling(self):
        # Reproduces the exact reported scenario: highest bid 6,47,000; Dealer 1 has an
        # active auto-bid ceiling of 8,00,000 (set BEFORE this competing bid, i.e. already
        # "dormant" — the bug claim was that it only ever fired once, at save time).
        auction = await database_sync_to_async(_mk_auction)(500000, 5000, highest_seed=647000)
        dealer1 = await database_sync_to_async(_mk_dealer)("dealer1")
        dealer2 = await database_sync_to_async(_mk_dealer)("dealer2")
        await database_sync_to_async(AutoBid.objects.create)(
            auction=auction, dealer=dealer1, max_amount=800000, is_active=True,
        )

        d1 = _connect(auction, dealer1)
        d2 = _connect(auction, dealer2)
        try:
            connected1, _ = await d1.connect()
            connected2, _ = await d2.connect()
            self.assertTrue(connected1)
            self.assertTrue(connected2)

            # Drain the initial 'state' snapshot both sockets get on connect.
            await d1.receive_json_from()
            await d2.receive_json_from()

            # Dealer 2 places a manual bid well under Dealer 1's ceiling.
            await d2.send_json_to({"type": "bid", "amount": 680000})

            # (Bug #2) The bidder's OWN socket must see the broadcast — proves group_send
            # actually fires for a manual bid, not just a local echo.
            msg_to_d2 = await d2.receive_json_from(timeout=2)
            self.assertEqual(msg_to_d2["type"], "bid")
            self.assertEqual(msg_to_d2["highest"], 680000)
            self.assertEqual(msg_to_d2["by_id"], dealer2.id)

            # (Bug #2) A DIFFERENT connected dealer's socket must ALSO see it, live, with no
            # refresh — this is the literal "you've been outbid" trigger on the client.
            msg_to_d1 = await d1.receive_json_from(timeout=2)
            self.assertEqual(msg_to_d1["type"], "bid")
            self.assertEqual(msg_to_d1["highest"], 680000)
            self.assertEqual(msg_to_d1["by_id"], dealer2.id)

            # (Bug #3) Dealer 1's ceiling must re-engage on THIS competing bid — not only at
            # the moment it was originally set — retaking the lead at the next valid
            # increment (680000 + 5000 = 685000), still under their 800000 ceiling.
            auto_msg_to_d1 = await d1.receive_json_from(timeout=2)
            self.assertEqual(auto_msg_to_d1["type"], "bid")
            self.assertEqual(auto_msg_to_d1["highest"], 685000)
            self.assertEqual(auto_msg_to_d1["by_id"], dealer1.id)

            # And Dealer 2 must see that counter-bid too, live, on the same socket used above.
            auto_msg_to_d2 = await d2.receive_json_from(timeout=2)
            self.assertEqual(auto_msg_to_d2["type"], "bid")
            self.assertEqual(auto_msg_to_d2["highest"], 685000)
            self.assertEqual(auto_msg_to_d2["by_id"], dealer1.id)

            # No further messages — the cascade must not overshoot Dealer 1's own ceiling
            # or keep firing once no one else can contest it.
            self.assertTrue(await d1.receive_nothing(timeout=0.3))
            self.assertTrue(await d2.receive_nothing(timeout=0.3))
        finally:
            await d1.disconnect()
            await d2.disconnect()

        # Source-of-truth check directly against the DB, independent of what the sockets saw.
        final_highest = await database_sync_to_async(lambda: auction.highest_bid)()
        self.assertEqual(final_highest.amount, 685000)
        self.assertEqual(final_highest.dealer_id, dealer1.id)

    async def test_ceiling_never_exceeded_and_stops_silently(self):
        # A tighter ceiling (6,80,000) that the competing bid already meets/exceeds must
        # NOT engage — auto-bid must never place a bid above its own ceiling, and must stop
        # without emitting any extra broadcast when it can't clear the floor.
        auction = await database_sync_to_async(_mk_auction)(500000, 5000, highest_seed=647000)
        dealer1 = await database_sync_to_async(_mk_dealer)("dealer1")
        dealer2 = await database_sync_to_async(_mk_dealer)("dealer2")
        await database_sync_to_async(AutoBid.objects.create)(
            auction=auction, dealer=dealer1, max_amount=680000, is_active=True,
        )

        d2 = _connect(auction, dealer2)
        try:
            connected2, _ = await d2.connect()
            self.assertTrue(connected2)
            await d2.receive_json_from()  # initial state

            await d2.send_json_to({"type": "bid", "amount": 680000})
            msg = await d2.receive_json_from(timeout=2)
            self.assertEqual(msg["highest"], 680000)
            self.assertEqual(msg["by_id"], dealer2.id)

            # Floor would now be 685000 > Dealer 1's 680000 ceiling — no counter-bid.
            self.assertTrue(await d2.receive_nothing(timeout=0.3))
        finally:
            await d2.disconnect()

        final_highest = await database_sync_to_async(lambda: auction.highest_bid)()
        self.assertEqual(final_highest.amount, 680000)
        self.assertEqual(final_highest.dealer_id, dealer2.id)
