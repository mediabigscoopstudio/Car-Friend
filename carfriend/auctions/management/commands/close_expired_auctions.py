from django.core.management.base import BaseCommand

from auctions.utils import auto_close_expired_auctions


class Command(BaseCommand):
    help = "Close all live auctions whose end_at has passed (status live -> closed)."

    def handle(self, *args, **options):
        n = auto_close_expired_auctions()
        self.stdout.write(self.style.SUCCESS(f"Closed {n} expired auction(s)."))
