"""allauth social adapter — skip the 'complete signup' confirmation page.

Google returns a verified email, so a social login should just create (or connect to)
the account and log in — never show allauth's bare intermediate signup form. The
seller/dealer role is applied right after by accounts.views.role_redirect (from the
session's intended_role), so nothing role-related needs to happen here.
"""
import logging

from allauth.account.utils import user_email
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

logger = logging.getLogger(__name__)


class CarFriendSocialAdapter(DefaultSocialAccountAdapter):

    def is_auto_signup_allowed(self, request, sociallogin):
        # Auto-create for social logins (Google email is verified) — never bounce the
        # user to the manual 'complete signup' form. pre_social_login already connected
        # any existing user by VERIFIED email (so we don't reach here for them). If an
        # account with this email still exists here, it means pre_social_login couldn't
        # safely connect it (unverified/ambiguous) — defer to allauth's default (the now-
        # styled form) rather than risk creating a duplicate account.
        email = (user_email(sociallogin.user) or "").strip().lower()
        if email:
            from accounts.models import User
            if User.objects.filter(email__iexact=email).exists():
                return super().is_auto_signup_allowed(request, sociallogin)
        return True

    def pre_social_login(self, request, sociallogin):
        """If this Google email already belongs to a user, CONNECT to them instead of
        creating a duplicate (or showing allauth's connect form). Only for a
        provider-verified email, so a login can't hijack an account by claiming an
        unverified address."""
        if sociallogin.is_existing:
            return
        email = (user_email(sociallogin.user) or "").strip().lower()
        if not email:
            return
        verified = any(
            (getattr(e, "email", "") or "").strip().lower() == email and e.verified
            for e in sociallogin.email_addresses
        )
        if not verified:
            return
        from accounts.models import User
        try:
            user = User.objects.get(email__iexact=email)
        except (User.DoesNotExist, User.MultipleObjectsReturned):
            return
        logger.info("social login: connecting Google account to existing user %s", user.pk)
        sociallogin.connect(request, user)
