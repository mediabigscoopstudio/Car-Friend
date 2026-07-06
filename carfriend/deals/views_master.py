"""Master (admin) document vault — READ-ONLY.

Admin can view/download the signed sale agreement (seller <-> dealer <-> Car Friend)
for a deal, searchable by vehicle number (same UX as payments_pending). No edits here.
"""
from django.shortcuts import render

from accounts.decorators import admin_required
from deals.models import Deal


@admin_required
def deal_documents(request):
    q = (request.GET.get("q") or "").strip()
    deals = (Deal.objects.select_related("vehicle", "seller", "dealer", "agreement")
             .filter(agreement__isnull=False).exclude(agreement__pdf="")
             .order_by("-id"))
    if q:
        deals = deals.filter(vehicle__plate_number__icontains=q)
    rows = []
    for d in deals[:300]:
        ag = getattr(d, "agreement", None)
        if not ag or not ag.pdf:
            continue
        rows.append({
            "deal": d,
            "vehicle": d.vehicle,
            "seller": (d.seller.get_full_name() or d.seller.username) if d.seller else "—",
            "dealer": (d.dealer.get_full_name() or d.dealer.username) if d.dealer else "—",
            "pdf_url": ag.pdf.url,
            "seller_signed": ag.seller_signed,
            "dealer_signed": ag.dealer_signed,
            "status": d.get_status_display(),
        })
    return render(request, "master/documents.html",
                  {"active": "documents", "rows": rows, "q": q, "count": len(rows)})
