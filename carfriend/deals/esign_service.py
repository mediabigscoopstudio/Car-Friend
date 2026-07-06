"""Aadhaar e-Sign orchestration (SurePass).

Real Aadhaar e-Sign via www.services (a separate SurePass product from KYC). There
is NO fake-sign fallback: `start_party_esign` returns SurePass's actual response so
the caller can surface it, and a party is marked signed ONLY by `complete_party_esign`
after SurePass confirms the transaction completed.
"""
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

VALID_PARTIES = ("seller", "dealer")


def _signer(deal, party):
    user = deal.seller if party == "seller" else deal.dealer
    if not user:
        return "", "", ""
    name = user.get_full_name() or user.username or ""
    return name, (getattr(user, "email", "") or ""), (getattr(user, "phone", "") or "")


def start_party_esign(agreement, party, *, pdf_url, callback_url):
    """Initiate SurePass Aadhaar e-Sign for one party. Stores the returned client_id as
    the party's PENDING e-Sign ref (NOT signed yet) and returns the structured SurePass
    result {ok, message, signing_url, client_id, ...} for the caller to surface."""
    from www.services import esign_initialize
    deal = agreement.deal
    name, email, phone = _signer(deal, party)
    result = esign_initialize(
        pdf_url=pdf_url, signer_name=name, signer_email=email, signer_phone=phone,
        reference=f"deal-{deal.id}-{party}", callback_url=callback_url)
    logger.info("SurePass e-Sign init deal=%s party=%s ok=%s status=%s msg=%s",
                deal.id, party, result.get("ok"), result.get("status"), result.get("message"))
    if result.get("ok") and result.get("client_id"):
        # Record the transaction ref now (pending); completion flips the signed flag.
        if party == "seller":
            agreement.seller_esign_ref = result["client_id"][:120]
            agreement.save(update_fields=["seller_esign_ref"])
        else:
            agreement.dealer_esign_ref = result["client_id"][:120]
            agreement.save(update_fields=["dealer_esign_ref"])
    return result


def complete_party_esign(agreement, party, *, ref=None):
    """Mark a party signed once SurePass has confirmed completion. Idempotent — a second
    call is a no-op. Stores the ref + signed-at, regenerates the PDF, and when BOTH
    parties are signed sets the Deal to SIGNED and notifies. Returns True if newly signed."""
    from deals.models import Deal
    from deals.services import generate_agreement_pdf
    from notifications.services import notify

    deal = agreement.deal
    already = agreement.seller_signed if party == "seller" else agreement.dealer_signed
    if already:
        return False
    now = timezone.now()
    if party == "seller":
        agreement.seller_signed = True
        agreement.seller_signed_at = now
        if ref:
            agreement.seller_esign_ref = ref[:120]
        agreement.save(update_fields=["seller_signed", "seller_signed_at", "seller_esign_ref"])
    else:
        agreement.dealer_signed = True
        agreement.dealer_signed_at = now
        if ref:
            agreement.dealer_esign_ref = ref[:120]
        agreement.save(update_fields=["dealer_signed", "dealer_signed_at", "dealer_esign_ref"])

    # Regenerate the PDF so the e-Sign block reflects this signature.
    try:
        generate_agreement_pdf(deal)
    except Exception:
        logger.exception("agreement PDF regeneration failed for deal %s", deal.id)

    agreement.refresh_from_db()
    if agreement.seller_signed and agreement.dealer_signed and deal.status in (
            Deal.Status.OPEN, Deal.Status.AGREEMENT):
        deal.status = Deal.Status.SIGNED       # both signed → ready for payment (Step 5)
        deal.save(update_fields=["status", "updated_at"])
        if deal.seller:
            notify(deal.seller, "deal_confirmed", title="Agreement signed by both parties",
                   body=f"{deal.vehicle.display_name} — your sale agreement is fully signed.",
                   url=f"/deals/{deal.id}/agreement/")
        if deal.dealer:
            notify(deal.dealer, "deal_confirmed", title="Agreement signed by both parties",
                   body=f"{deal.vehicle.display_name} — the agreement is fully signed.",
                   url=f"/deals/{deal.id}/agreement/dealer/")
    return True
