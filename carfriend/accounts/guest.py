"""Phone-keyed guest accounts + Google-login merge helpers.

Identity model (option a): the verified phone number is the primary identity.
A guest account is a normal User with is_guest=True and an unusable password,
keyed by phone. When the same person later signs in with Google, their guest
cars are merged onto the real account by matching the verified phone.
"""

import logging

from .models import Role, User

logger = logging.getLogger(__name__)


def normalise_phone(phone):
    """Keep digits only; drop a leading 91 country code for 12-digit inputs."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    return digits


def get_or_create_guest_user(phone):
    """Find or create the phone-keyed account for a verified phone.

    If a real (non-guest) account already owns this phone, that account is
    returned. Otherwise a guest seller account is created.
    """
    phone = normalise_phone(phone)
    if not phone:
        raise ValueError("phone required")

    existing = User.objects.filter(phone=phone).order_by("is_guest", "id").first()
    if existing:
        if not existing.phone_verified:
            existing.phone_verified = True
            existing.save(update_fields=["phone_verified"])
        return existing

    username = f"guest_{phone}"
    # Guarantee username uniqueness even in odd states.
    suffix = 0
    base = username
    while User.objects.filter(username=username).exists():
        suffix += 1
        username = f"{base}_{suffix}"

    user = User(
        username=username,
        phone=phone,
        phone_verified=True,
        is_guest=True,
        role=Role.SELLER,
    )
    user.set_unusable_password()
    user.save()
    logger.info("Created guest account for phone-keyed identity (user id=%s)", user.id)
    return user


def merge_guest_cars_into(user):
    """Move cars from any guest account(s) sharing this user's verified phone
    onto ``user`` so they appear under the real account's "my cars".

    Returns the number of cars moved. No-op unless the user has a verified phone.
    """
    if not user or not getattr(user, "phone", "") or not getattr(user, "phone_verified", False):
        return 0

    # Avoid acting on the guest record itself.
    if getattr(user, "is_guest", False):
        return 0

    from vehicles.models import Vehicle  # imported lazily to avoid app-load cycle

    phone = normalise_phone(user.phone)
    guests = User.objects.filter(phone=phone, is_guest=True).exclude(pk=user.pk)

    moved = 0
    for guest in guests:
        vehicles = Vehicle.objects.filter(seller=guest)
        for vehicle in vehicles:
            vehicle.seller = user
            vehicle.save(update_fields=["seller"])
            # keep the auto-created lead pointing at the real account
            lead = getattr(vehicle, "lead", None)
            if lead and lead.seller_id != user.pk:
                lead.seller = user
                lead.save(update_fields=["seller"])
            moved += 1
        # Park the now-empty guest so it can't be reused as a duplicate identity.
        guest.is_active = False
        guest.save(update_fields=["is_active"])

    if moved:
        logger.info("Merged %s guest car(s) onto user id=%s", moved, user.id)
    return moved
