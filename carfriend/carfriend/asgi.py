import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "carfriend.settings")

django_asgi = get_asgi_application()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path

from auctions.consumers import AuctionConsumer
from inspections.consumers import DriveConsumer

application = ProtocolTypeRouter({
    "http": django_asgi,
    "websocket": AuthMiddlewareStack(
        URLRouter([
            path("ws/auction/<auction_id>/", AuctionConsumer.as_asgi()),
            path("ws/drive/<report_id>/", DriveConsumer.as_asgi()),
        ])
    ),
})
