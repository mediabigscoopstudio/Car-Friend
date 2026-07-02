import json

from channels.generic.websocket import AsyncWebsocketConsumer


class DriveConsumer(AsyncWebsocketConsumer):
    """Read-only live test-drive watch (Admin / customer views).

    The inspector's test-drive saves broadcast to the 'drive_<report_id>' group
    (views_app._drive_broadcast, gated by settings.DRIVE_LIVE_BROADCAST). This
    consumer only relays those events to watchers — it never accepts input, so it
    is fully isolated from the auction bidding consumer.
    """

    async def connect(self):
        self.report_id = self.scope["url_route"]["kwargs"]["report_id"]
        self.group = f"drive_{self.report_id}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive(self, text_data):
        return  # read-only

    async def drive_event(self, event):
        await self.send(json.dumps(event["payload"]))
