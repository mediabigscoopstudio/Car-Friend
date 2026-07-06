"""Deal creation service.

`create_deal_from_win()` is the single place a Deal is created when a seller
ACCEPTS a winning price — from a live auction's highest bid OR a selected OCB
offer. Both accept paths converge here, so the money split lives in exactly one
place.

It splits the winning GROSS price back to the seller's BASE via core.margin
(spec §2 / §2.6): the dealer pays GROSS, the seller is shown/paid BASE, and the
margin + GST is CarFriend's cut (recorded on the Deal). The RC amount
(CF_RC_HOLD) is a SEPARATE payment (Step 5) and is only *recorded* here as an
additional charge — it is NOT folded into grand_total.

Idempotent: one active Deal per vehicle. Does NOT create Payment rows (Step 5)
and does NOT touch the agreement / e-sign (Step 4).
"""
from django.conf import settings

import io
import logging

from django.core.files.base import ContentFile

from core.margin import base_from_gross
from deals.models import Deal, DealAgreement
from notifications.services import notify

logger = logging.getLogger(__name__)


def create_deal_from_win(vehicle, winning_gross, dealer, seller, assigned_sales=None):
    """Create — or return the existing — Deal for `vehicle` from a winning GROSS
    price. Returns the Deal.

    Idempotent: if a non-closed Deal already exists for the vehicle it is returned
    unchanged (never two active Deals for one car). Money fields are derived from
    core.margin.base_from_gross(winning_gross):

        final_price        = winning_gross            # dealer's gross price
        seller_shown_price = base                     # seller's base (payout)
        cf_commission      = margin
        gst_percentage     = settings.CF_GST_PERCENT
        gst_amount         = gst
        grand_total        = winning_gross            # RC is a SEPARATE payment
        additional_charges = [{"label": "RC transfer", "amount": CF_RC_HOLD}]
        status             = 'agreement'              # awaiting agreement / e-sign
    """
    existing = (Deal.objects.filter(vehicle=vehicle)
                .exclude(status=Deal.Status.CLOSED).order_by("-id").first())
    if existing:
        return existing

    winning_gross = int(winning_gross or 0)
    split = base_from_gross(winning_gross)
    deal = Deal.objects.create(
        vehicle=vehicle,
        seller=seller,
        dealer=dealer,
        assigned_sales=assigned_sales,
        final_price=winning_gross,
        seller_shown_price=split["base"],
        cf_commission=split["margin"],
        gst_percentage=settings.CF_GST_PERCENT,
        gst_amount=split["gst"],
        grand_total=winning_gross,
        additional_charges=[{"label": "RC transfer", "amount": int(settings.CF_RC_HOLD)}],
        status=Deal.Status.AGREEMENT,
    )

    # Lead -> seller_approved (deal created, heading to agreement). Forward-only:
    # for an OCB lead already at the same rank this is a harmless no-op.
    from crm.services import transition_lead_for_vehicle
    transition_lead_for_vehicle(vehicle, "seller_approved", actor=seller)

    # Seller sees BASE; dealer sees GROSS (the gross/base invariant).
    if seller:
        notify(seller, "deal_confirmed",
               title=f"Sale confirmed: {vehicle.display_name}",
               body=f"You'll receive ₹{split['base']:,}. Your agreement is being prepared.")
    if dealer:
        notify(dealer, "deal_confirmed",
               title=f"You won: {vehicle.display_name}",
               body=f"Deal for ₹{winning_gross:,}. Your agreement is being prepared.")

    # Generate the sale-agreement PDF (Agreement stage) with the real deal data. Never
    # let a PDF hiccup block deal creation — log and continue.
    try:
        generate_agreement_pdf(deal)
    except Exception:
        logger.exception("agreement PDF generation failed for deal %s", deal.id)
    return deal


# ── Agreement PDF (approved 3-part layout, real deal data) ────────────────────

def _agreement_party(user, *, is_dealer):
    """Party block for the agreement. PAN / masked-Aadhaar / GST come from the user's
    KYC records (masked values only). Never raises on missing data."""
    if not user:
        return {"name": "—", "phone": "—", "address": "—", "pan": "—",
                "gst": "—", "aadhaar": "—", "kyc": "Pending"}
    from kyc.models import KYCVerification
    prof = getattr(user, "dealer_profile", None) if is_dealer else getattr(user, "seller_profile", None)
    kmap = {}
    for r in KYCVerification.objects.filter(subject=user).order_by("-created_at"):
        kmap.setdefault(r.kind, r.masked_value or "")
    name = (user.get_full_name() or user.username or "—")
    address = (getattr(prof, "address", "") if prof else "") or (getattr(user, "city", "") or "")
    row = {
        "name": name,
        "phone": getattr(user, "phone", "") or "—",
        "address": address or "—",
        "pan": kmap.get(KYCVerification.Kind.PAN, "") or "—",
        "kyc": "Verified" if getattr(user, "is_kyc_done", False) else "Pending",
    }
    if is_dealer:
        row["name"] = (getattr(prof, "dealership_name", "") if prof else "") or name
        row["gst"] = (getattr(prof, "gstin", "") if prof else "") or kmap.get(KYCVerification.Kind.GST, "") or "—"
    else:
        row["aadhaar"] = kmap.get(KYCVerification.Kind.AADHAAR, "") or "—"
    return row


def _vehicle_grade(vehicle):
    try:
        from inspections.models import InspectionReport
        r = (InspectionReport.objects.filter(visit__vehicle=vehicle)
             .order_by("-id").only("condition_grade").first())
        return (r.condition_grade if r and r.condition_grade else "—")
    except Exception:
        return "—"


# Placeholder clause headings — bodies stay as labelled placeholders until Car Friend
# supplies the wording (we never invent legal text, nor copy any third party's).
_POLICY_CLAUSES = ["1. Scope of the platform", "2. Facilitation & settlement",
                   "3. Payments & seller payout", "4. RC transfer", "5. Cancellations",
                   "6. Liability", "7. Data & privacy"]
_TERMS_CLAUSES = ["1. Ownership & title", "2. Vehicle condition & disclosures",
                  "3. Dues, challans & liabilities", "4. Handover & documents",
                  "5. Payment terms", "6. Warranties & disclaimers",
                  "7. Dispute resolution", "8. Governing law",
                  "9. Execution by Aadhaar e-Sign"]


def generate_agreement_pdf(deal):
    """Render the Car Friend sale agreement (approved 3-part layout) with the REAL deal
    data and store it on deal.agreement.pdf. Regenerated after e-Sign so the e-Sign
    block reflects the SurePass refs + timestamps. Returns the FileField or None.

    ONE canonical legal PDF records the actual TRANSACTED figures (gross + RC + total);
    seller-facing BASE vs dealer-facing GROSS scoping lives in the app UI, not in two
    forged PDFs (per spec §6)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.utils import simpleSplit
        from reportlab.pdfgen import canvas
    except ImportError:
        logger.warning("reportlab not installed — cannot generate agreement PDF")
        return None
    from django.utils import timezone

    agreement, _ = DealAgreement.objects.get_or_create(deal=deal)
    v = deal.vehicle
    seller = _agreement_party(deal.seller, is_dealer=False)
    dealer = _agreement_party(deal.dealer, is_dealer=True)
    entity  = getattr(settings, "CF_LEGAL_ENTITY", "Car Friend")
    address = getattr(settings, "CF_LEGAL_ADDRESS", "")
    rc = int(getattr(settings, "CF_RC_HOLD", 5000))
    gross = int(deal.final_price or 0)
    total = gross + rc

    GREEN, BRIGHT = (0x15/255, 0x60/255, 0x3E/255), (0x1F/255, 0xA4/255, 0x63/255)
    buf = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buf, pagesize=A4)
    st = {"y": 0.0, "page": 0}

    def rupees(n):  # ASCII 'Rs.' — Helvetica has no rupee glyph
        return f"Rs. {int(n):,}"

    def footer():
        c.setFillGray(0.45); c.setFont("Helvetica", 7)
        foot = entity + (f"  |  {address}" if address else "")
        c.drawString(18*mm, 12*mm, foot[:135])
        c.drawRightString(W - 18*mm, 12*mm, f"Page {st['page']}")

    def new_page(title=None):
        if st["page"] > 0:
            footer(); c.showPage()
        st["page"] += 1
        c.setFillColorRGB(*GREEN); c.rect(0, H - 26*mm, W, 26*mm, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 16); c.drawString(18*mm, H - 13*mm, "CAR FRIEND")
        c.setFont("Helvetica", 8);       c.drawString(18*mm, H - 18.5*mm, entity)
        c.drawRightString(W - 18*mm, H - 12*mm, f"Agreement #{deal.id:06d}")
        c.drawRightString(W - 18*mm, H - 16.5*mm, timezone.now().strftime("%d %b %Y"))
        st["y"] = H - 34*mm
        if title:
            heading(title)

    def ensure(space):
        if st["y"] - space < 20*mm:
            new_page()

    def heading(txt):
        ensure(13*mm)
        c.setFillColorRGB(*GREEN); c.setFont("Helvetica-Bold", 12)
        c.drawString(18*mm, st["y"], txt)
        c.setStrokeColorRGB(*BRIGHT); c.setLineWidth(1)
        c.line(18*mm, st["y"] - 2*mm, W - 18*mm, st["y"] - 2*mm)
        st["y"] -= 8*mm

    def subheading(txt):
        ensure(9*mm)
        c.setFillColorRGB(0.12, 0.14, 0.13); c.setFont("Helvetica-Bold", 10)
        c.drawString(18*mm, st["y"], txt); st["y"] -= 5*mm

    def kv(label, value):
        ensure(6*mm)
        c.setFillColorRGB(0.42, 0.42, 0.42); c.setFont("Helvetica", 8.5)
        c.drawString(20*mm, st["y"], label)
        c.setFillColorRGB(0.12, 0.14, 0.13); c.setFont("Helvetica-Bold", 9)
        c.drawString(64*mm, st["y"], str(value)); st["y"] -= 5.6*mm

    def para(txt, size=8.5, gap=3*mm):
        c.setFillColorRGB(0.3, 0.3, 0.3); c.setFont("Helvetica", size)
        for line in simpleSplit(txt, "Helvetica", size, W - 40*mm):
            ensure(5*mm)
            c.drawString(20*mm, st["y"], line); st["y"] -= (size + 2.2)
        st["y"] -= gap

    def _fmt(dt):
        return timezone.localtime(dt).strftime("%d %b %Y, %H:%M") if dt else "—"

    # ── Part 1 — Vehicle Delivery Acknowledgment Receipt ──
    new_page("Part 1 - Vehicle Delivery Acknowledgment Receipt")
    para(f"This receipt acknowledges the sale and delivery of the vehicle described below, "
         f"facilitated by {entity} (\"Car Friend\") between the Seller and the Buyer / Dealer named herein.")
    heading("Parties")
    kv("Seller", seller["name"]); kv("Phone", seller["phone"]); kv("Address", seller["address"])
    kv("PAN", seller["pan"]); kv("Aadhaar (masked)", seller["aadhaar"]); kv("KYC", seller["kyc"])
    st["y"] -= 2*mm
    kv("Buyer / Dealer", dealer["name"]); kv("Phone", dealer["phone"]); kv("Address", dealer["address"])
    kv("PAN", dealer["pan"]); kv("GST", dealer["gst"]); kv("KYC", dealer["kyc"])
    st["y"] -= 2*mm
    kv("Facilitator", entity)
    heading("Vehicle")
    kv("Registration", v.plate_number or "—")
    kv("Make / Model", (f"{v.make} {v.model}".strip() or "—"))
    kv("Year", v.year or "—")
    kv("Fuel", getattr(v, "fuel", "") or "—")
    kv("Transmission", getattr(v, "transmission", "") or "—")
    kv("Condition grade", _vehicle_grade(v))
    heading("Transaction")
    kv("Vehicle amount (gross)", rupees(gross))
    kv("RC transfer", rupees(rc))
    kv("Total", rupees(total))
    kv("Payment status", deal.get_status_display())
    heading("Aadhaar e-Sign (SurePass)")
    para("Executed by Aadhaar-based electronic signature (SurePass e-Sign). The earlier "
         "OTP-based execution is replaced by Aadhaar e-Sign; each party's signature is "
         "recorded below with its SurePass transaction reference, timestamp and status.")
    for who, signed, ref, ts in (
        ("Seller", agreement.seller_signed, agreement.seller_esign_ref,
         getattr(agreement, "seller_signed_at", None)),
        ("Buyer / Dealer", agreement.dealer_signed, agreement.dealer_esign_ref,
         getattr(agreement, "dealer_signed_at", None)),
    ):
        subheading(who)
        kv("Status", "Signed" if signed else "Pending")
        kv("e-Sign ref", ref or "—")
        kv("Signed at", _fmt(ts))

    # ── Part 2 — Car Friend Policy ──
    new_page("Part 2 - Car Friend Policy")
    for h in _POLICY_CLAUSES:
        subheading(h)
        para("[Policy text to be provided by Car Friend.]")

    # ── Part 3 — Terms & Conditions ──
    new_page("Part 3 - Terms & Conditions")
    for h in _TERMS_CLAUSES:
        subheading(h)
        para("[Clause text to be provided by Car Friend.]")

    footer(); c.showPage(); c.save()
    agreement.pdf.save(f"agreement_{deal.id}.pdf", ContentFile(buf.getvalue()), save=True)
    return agreement.pdf
