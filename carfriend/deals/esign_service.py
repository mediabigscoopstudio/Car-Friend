"""Stubbed e-sign provider.

Clean hook so a real Aadhaar e-Sign (Digio / NSDL) can replace the internals
later with NO change to callers. `sign()` currently returns a fake reference id.
"""

import logging
import uuid

logger = logging.getLogger(__name__)


def sign(document_label, signer_email=""):
    """Return a provider reference id for a signature request.

    STUB: returns a fake id. Replace the body with the real e-sign API call —
    the args and return type stay the same.
    """
    ref = f"ESIGN-STUB-{uuid.uuid4().hex[:16].upper()}"
    logger.info("[esign stub] signed %s for %s -> %s", document_label, signer_email or "?", ref)
    return ref


def sign_agreement(agreement, party):
    """Sign a deals.DealAgreement on behalf of ``party`` ('seller' | 'dealer').

    Stores the (stub) reference, flips the signed flag, and returns the ref.
    """
    deal = agreement.deal
    if party == "seller":
        ref = sign(f"deal:{deal.id}:seller", getattr(deal.seller, "email", ""))
        agreement.seller_esign_ref = ref
        agreement.seller_signed = True
        agreement.save(update_fields=["seller_esign_ref", "seller_signed"])
    elif party == "dealer":
        ref = sign(f"deal:{deal.id}:dealer", getattr(deal.dealer, "email", ""))
        agreement.dealer_esign_ref = ref
        agreement.dealer_signed = True
        agreement.save(update_fields=["dealer_esign_ref", "dealer_signed"])
    else:
        raise ValueError("party must be 'seller' or 'dealer'")
    return ref
