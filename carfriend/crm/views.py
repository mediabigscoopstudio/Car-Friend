import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.decorators import retail_required, role_required
from core.models import log
from notifications.services import notify
from .models import Lead, NegotiationOffer, CommunicationLog, Task


@role_required("retail", "sales", "admin")
def pipeline(request):
    qs = Lead.objects.select_related("seller", "vehicle").order_by("-created_at")
    if not request.user.is_admin:
        qs = qs.filter(assigned_to=request.user)
    columns = [
        {"key": s, "label": label, "leads": list(qs.filter(stage=s))}
        for s, label in Lead.Stage.choices
    ]
    return render(request, "teams/pipeline.html",
                  {"columns": columns, "total": qs.count(), "active": "pipeline"})


@retail_required
def seller_detail(request, id):
    lead = get_object_or_404(Lead, id=id)
    margin_hint = 0
    if lead.vehicle:
        margin_hint = lead.vehicle.est_market_value - lead.expected_price
    return render(request, "teams/seller.html", {
        "active":      "pipeline",
        "lead":        lead,
        "vehicle":     lead.vehicle,
        "offers":      lead.offers.all(),
        "comms":       lead.comms.all(),
        "margin_hint": margin_hint,
    })


@retail_required
def lead_move(request, id):
    if request.method != "POST":
        return redirect(f"/seller/{id}")
    lead = get_object_or_404(Lead, id=id)
    lead.stage = request.POST["stage"]
    lead.save()
    log(request.user, "lead.move", lead, request, stage=lead.stage)
    return redirect(f"/seller/{id}")


@retail_required
def add_offer(request, id):
    if request.method != "POST":
        return redirect(f"/seller/{id}")
    lead = get_object_or_404(Lead, id=id)
    price = int(request.POST["offer_price"])
    NegotiationOffer.objects.create(lead=lead, offer_price=price, by=request.user)
    lead.stage = "negotiation"
    lead.save()
    notify(
        lead.seller, "doc_pending",
        title="New price offer",
        body=f"₹{price:,} offered for your car.",
    )
    return redirect(f"/seller/{id}")


@retail_required
def create_auction(request, id):
    from auctions.models import Auction, AUCTION_MINUTES

    lead = get_object_or_404(Lead, id=id)
    if request.method == "POST":
        start = timezone.now()
        a = Auction.objects.create(
            vehicle=lead.vehicle,
            reserve_price=int(request.POST["reserve_price"]),
            start_at=start,
            end_at=start + datetime.timedelta(minutes=AUCTION_MINUTES),
            min_increment=int(request.POST.get("min_increment", 5000)),
            status="live",
            created_by=request.user,
        )
        lead.stage = "auction_made"
        lead.save()
        log(request.user, "auction.create", a, request)
        notify(
            lead.seller, "auction_start",
            title=f"Auction live: {lead.vehicle.title}",
            body="Your car is now in a live 30-minute auction.",
        )
        return redirect("/pipeline")
    return render(request, "teams/create_auction.html", {"active": "pipeline", "lead": lead})


@role_required("retail", "sales")
def add_comm(request):
    if request.method == "POST":
        CommunicationLog.objects.create(
            lead_id=request.POST.get("lead_id") or None,
            dealer_id=request.POST.get("dealer_id") or None,
            vehicle_id=request.POST.get("vehicle_id") or None,
            kind=request.POST.get("kind", "note"),
            body=request.POST["body"],
            by=request.user,
        )
    return redirect(request.META.get("HTTP_REFERER", "/pipeline"))


@role_required("retail", "sales")
def tasks(request):
    return render(
        request, "teams/tasks.html",
        {"active": "tasks", "tasks": Task.objects.filter(assigned_to=request.user)},
    )


@role_required("retail", "sales")
def add_task(request):
    if request.method == "POST":
        Task.objects.create(
            title=request.POST["title"],
            kind=request.POST.get("kind", "followup"),
            assigned_to_id=request.POST.get("assigned_to") or request.user.id,
            lead_id=request.POST.get("lead_id") or None,
            due_at=request.POST.get("due_at") or None,
            created_by=request.user,
        )
    return redirect("/tasks")


@role_required("retail", "sales")
def task_done(request, id):
    t = get_object_or_404(Task, id=id)
    t.status = "done"
    t.save()
    return redirect("/tasks")
