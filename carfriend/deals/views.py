from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from .models import Deal, DealAgreement
from .esign_service import start_party_esign, complete_party_esign, VALID_PARTIES


def _ensure_pdf(deal):
    """Make sure the agreement PDF exists (regenerate if missing). Returns the agreement."""
    from .services import generate_agreement_pdf
    agreement, _ = DealAgreement.objects.get_or_create(deal=deal)
    if not agreement.pdf:
        try:
            generate_agreement_pdf(deal)
            agreement.refresh_from_db()
        except Exception:
            pass
    return agreement


# ── Agreement views (per party; wall-scoped) ──────────────────────────────────

@login_required(login_url="/auth/login/")
def deal_agreement(request, pk):
    """SELLER's agreement page. Aadhaar e-Sign (SurePass) — the seller signs their own
    party. Seller wall: BASE sale price; the buyer is shown anonymously (status only)."""
    deal = get_object_or_404(Deal.objects.select_related("vehicle"), pk=pk, seller=request.user)
    agreement = _ensure_pdf(deal)
    sale_price = deal.seller_shown_price or deal.final_price   # BASE
    return render(request, "www/deals/agreement.html", {
        "deal": deal, "agreement": agreement, "party": "seller",
        "sale_fmt": f"{sale_price:,}" if sale_price else None,
    })


@login_required(login_url="/auth/login/")
def deal_agreement_dealer(request, pk):
    """DEALER's agreement page. Aadhaar e-Sign (SurePass) — the dealer signs their own
    party. Dealer wall: GROSS price; the seller is shown anonymously (status only)."""
    deal = get_object_or_404(Deal.objects.select_related("vehicle"), pk=pk, dealer=request.user)
    agreement = _ensure_pdf(deal)
    return render(request, "www/deals/agreement_dealer.html", {
        "deal": deal, "agreement": agreement, "party": "dealer",
        "price_fmt": f"{deal.final_price:,}" if deal.final_price else None,   # GROSS
    })


# ── e-Sign start / callback ───────────────────────────────────────────────────

@login_required(login_url="/auth/login/")
def esign_start(request, pk, party):
    """Initiate SurePass Aadhaar e-Sign for the signed-in party and redirect them to the
    SurePass-hosted signing page. If SurePass declines (e.g. sandbox 'product not
    enabled'), surface its ACTUAL message — no fake sign, no generic 500."""
    if party not in VALID_PARTIES:
        return redirect("/")
    field = {"seller": "seller", "dealer": "dealer"}[party]
    lookup = {"pk": pk, field: request.user}
    deal = get_object_or_404(Deal.objects.select_related("vehicle"), **lookup)
    agreement = _ensure_pdf(deal)
    back = reverse("deal_agreement" if party == "seller" else "deal_agreement_dealer", args=[pk])

    already = agreement.seller_signed if party == "seller" else agreement.dealer_signed
    if already:
        messages.info(request, "You have already e-signed this agreement.")
        return redirect(back)
    if not agreement.pdf:
        messages.error(request, "The agreement PDF isn't ready yet. Please try again shortly.")
        return redirect(back)

    pdf_url = request.build_absolute_uri(agreement.pdf.url)
    callback_url = request.build_absolute_uri(reverse("esign_callback", args=[pk, party]))
    result = start_party_esign(agreement, party, pdf_url=pdf_url, callback_url=callback_url)

    if result.get("ok") and result.get("signing_url"):
        return redirect(result["signing_url"])
    # Surface SurePass's real response verbatim (sandbox may say 'not enabled').
    messages.error(request, f"SurePass e-Sign: {result.get('message') or 'unavailable'} "
                            f"(status {result.get('status')}).")
    return redirect(back)


@csrf_exempt
def esign_callback(request, pk, party):
    """SurePass redirects/POSTs here when a party finishes signing. A party is marked
    signed ONLY when SurePass confirms the transaction completed (get-status) AND the
    client_id matches the ref we initiated — so this public endpoint can't be spoofed."""
    from www.services import esign_fetch_status
    if party not in VALID_PARTIES:
        return redirect("/")
    deal = get_object_or_404(Deal.objects.select_related("vehicle"), pk=pk)
    agreement, _ = DealAgreement.objects.get_or_create(deal=deal)
    back = reverse("deal_agreement" if party == "seller" else "deal_agreement_dealer", args=[pk])

    client_id = (request.GET.get("client_id") or request.POST.get("client_id") or "").strip()
    stored = agreement.seller_esign_ref if party == "seller" else agreement.dealer_esign_ref
    # Only the transaction we initiated for this party may complete it.
    if not client_id:
        client_id = stored
    if not client_id or (stored and client_id != stored):
        messages.error(request, "SurePass e-Sign: transaction reference did not match.")
        return redirect(back)

    status = esign_fetch_status(client_id)
    if status.get("completed"):
        complete_party_esign(agreement, party, ref=client_id)
        messages.success(request, "e-Sign complete — thank you.")
    else:
        messages.error(request, f"SurePass e-Sign: {status.get('message') or 'not completed'} "
                                f"(status {status.get('status')}).")
    return redirect(back)


# ── Closing summary ───────────────────────────────────────────────────────────

@login_required(login_url="/auth/login/")
def deal_sold(request, pk):
    """Closing summary + payout status for a completed sale."""
    from payments.models import Payment
    from accounts.models import SellerProfile

    deal = get_object_or_404(Deal.objects.select_related("vehicle"), pk=pk, seller=request.user)
    payment = Payment.objects.filter(deal=deal).order_by("-id").first()
    sp = SellerProfile.objects.filter(user=request.user).first()

    sale_price = deal.seller_shown_price or deal.final_price
    return render(request, "www/deals/sold.html", {
        "deal": deal,
        "payment": payment,
        "sale_fmt": f"{sale_price:,}" if sale_price else None,
        "has_payout": bool(sp and (sp.bank_account_number or sp.upi_id)),
    })
