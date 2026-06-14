"""On any login (including Google/allauth), pull guest cars that match the
account's verified phone onto the real account. No-op for guests or accounts
without a verified phone, so it is safe to run on every login."""

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .guest import merge_guest_cars_into


@receiver(user_logged_in)
def merge_guest_cars_on_login(sender, request, user, **kwargs):
    try:
        merge_guest_cars_into(user)
    except Exception:  # never block login on a merge hiccup
        pass
