from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import Deal, DealAgreement


@login_required(login_url="/auth/login/")
def deal_agreement(request, pk):
    """Seller reviews and e-signs the sale agreement. e-Sign here is in-app typed
    consent (tick + typed legal name) — it records seller_signed + a reference on
    the existing DealAgreement, and advances the deal to 'signed'. This is app
    consent, not an Aadhaar-grade e-sign integration."""
    deal = get_object_or_404(Deal.objects.select_related("vehicle"), pk=pk, seller=request.user)
    agreement, _ = DealAgreement.objects.get_or_create(deal=deal)

    error = None
    if request.method == "POST" and not agreement.seller_signed:
        name  = (request.POST.get("full_name") or "").strip()
        agree = request.POST.get("agree")
        if not agree or not name:
            error = "Tick the box and type your full name to e-sign."
        else:
            stamp = timezone.now().isoformat(timespec="seconds")
            agreement.seller_signed = True
            agreement.seller_esign_ref = (f"typed:{name}|{stamp}")[:120]
            agreement.save(update_fields=["seller_signed", "seller_esign_ref"])
            if deal.status in (Deal.Status.OPEN, Deal.Status.AGREEMENT):
                deal.status = Deal.Status.SIGNED
                deal.save(update_fields=["status", "updated_at"])
            return redirect("deal_agreement", pk=deal.pk)

    sale_price = deal.seller_shown_price or deal.final_price
    return render(request, "www/deals/agreement.html", {
        "deal": deal,
        "agreement": agreement,
        "error": error,
        "sale_fmt": f"{sale_price:,}" if sale_price else None,
    })


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
