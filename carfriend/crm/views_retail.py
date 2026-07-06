"""Retail Associate (teams host) — Lead Pipeline, OCB board, Task Manager.

Role-scoped: every view requires role == retail (or admin/superuser); a
wrong-role user is redirected to their own dashboard, an anonymous user to the
teams login. Retail only ever sees its OWN leads / OCBs / tasks.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Role, User
from auctions.models import Auction, OCBListing, OCBMessage, OCBOffer
from auctions.ocb_services import offer_rows, offer_to_winner
from crm.models import Lead, Task
from deals.models import Deal
from notifications.services import notify

# 8 pipeline columns (un-qualified is the Lead Manager's, not shown here).
RETAIL_STAGES = [
    Lead.STAGE_NEW, Lead.STAGE_QUALIFIED, Lead.STAGE_INSP_SCHED, Lead.STAGE_INSP_DONE,
    Lead.STAGE_APPROVED, Lead.STAGE_NEGOTIATION, Lead.STAGE_AUCTION, Lead.STAGE_CLOSED,
]
_STAGE_LABELS = dict(Lead.STAGE_CHOICES)


def _require_retail(request):
    if not request.user.is_authenticated:
        return redirect("/auth/login/")
    if request.user.role != User.ROLE_RETAIL and not request.user.is_superuser:
        from accounts.views import get_dashboard_url
        return redirect(get_dashboard_url(request.user))
    return None


def _car(vehicle):
    if not vehicle:
        return "—"
    return f"{vehicle.make} {vehicle.model} {vehicle.year}".strip()


# ── Lead Pipeline ────────────────────────────────────────────────────────────

def retail_pipeline(request):
    guard = _require_retail(request)
    if guard:
        return guard
    leads = list(Lead.objects.filter(assigned_to=request.user).select_related("vehicle", "seller"))
    now = timezone.now()
    columns = []
    for stage in RETAIL_STAGES:
        cards = []
        for l in leads:
            if l.stage != stage:
                continue
            v = l.vehicle
            cards.append({
                "id": l.id,
                "seller": (l.seller.get_full_name() or l.seller.username) if l.seller else "—",
                "car": _car(v),
                "price": v.expected_price if v else None,
                "days": (now - l.updated_at).days,
                "stage_label": l.get_stage_display(),
            })
        columns.append({"label": _STAGE_LABELS.get(stage, stage), "count": len(cards), "cards": cards})
    return render(request, "teams/retail/pipeline.html", {"columns": columns})


def retail_lead_detail(request, lead_id):
    guard = _require_retail(request)
    if guard:
        return guard
    lead = get_object_or_404(Lead.objects.select_related("vehicle", "seller"),
                             id=lead_id, assigned_to=request.user)
    can_ocb = lead.stage in (Lead.STAGE_NEGOTIATION, Lead.STAGE_AUCTION,
                             Lead.STAGE_AUCTION_LIVE, Lead.STAGE_AUCTION_CLOSED)
    existing_ocb = (OCBListing.objects.filter(vehicle=lead.vehicle).order_by("-created_at").first()
                    if lead.vehicle else None)
    # An allocated (Assigned) lead can be sent to auction by its retail associate.
    can_auction = lead.stage == Lead.STAGE_ASSIGNED
    return render(request, "teams/retail/lead_detail.html", {
        "lead": lead, "can_ocb": can_ocb, "existing_ocb": existing_ocb,
        "can_auction": can_auction, "car": _car(lead.vehicle),
    })


@require_POST
def retail_lead_create_ocb(request, lead_id):
    """The lead's ASSIGNED Retail Associate creates this lead's OCB — the SOLE
    OCB-creation path. HARD ownership: only lead.assigned_associate may create;
    everyone else gets 403. assigned_to is stamped to request.user, so an OCB can
    NEVER be orphaned. Idempotent — one active OCB per vehicle. The RA supplies the
    seller-facing BASE (defaulting to the seller's suggested price); it is stored
    GROSS via core.margin. Offered to the auction winner first (winner-first tier)."""
    from django.http import HttpResponseForbidden
    from core.margin import gross_breakdown
    guard = _require_retail(request)
    if guard:
        return guard
    lead = get_object_or_404(Lead.objects.select_related("vehicle"), id=lead_id)
    if lead.assigned_associate_id != request.user.id:
        return HttpResponseForbidden("Only the assigned Retail Associate can create this lead's OCB.")
    if not lead.vehicle:
        messages.error(request, "This lead has no vehicle.")
        return redirect(f"/pipeline/{lead.id}/")
    # Idempotent — never two active OCBs per vehicle.
    existing = (OCBListing.objects.filter(vehicle=lead.vehicle)
                .exclude(status__in=[OCBListing.Status.AGREEMENT, OCBListing.Status.REJECTED,
                                     OCBListing.Status.ACCEPTED])
                .order_by("-id").first())
    if existing:
        messages.info(request, "An OCB already exists for this lead.")
        return redirect(f"/pipeline/{lead.id}/")
    raw = (request.POST.get("base_price") or "").replace(",", "").replace("₹", "").strip()
    try:
        base = int(float(raw))
    except (TypeError, ValueError):
        base = 0
    if base <= 0:
        messages.error(request, "Enter a valid client price (base).")
        return redirect(f"/pipeline/{lead.id}/")
    auction = Auction.objects.filter(vehicle=lead.vehicle).order_by("-created_at").first()
    ocb = OCBListing.objects.create(
        vehicle=lead.vehicle, auction=auction,
        ocb_price=gross_breakdown(base)["gross"],   # store dealer-facing GROSS
        assigned_to=request.user,                   # the assigned RA owns it — never null
        status=OCBListing.Status.OPEN)
    offer_to_winner(ocb, actor=request.user)        # winner-first tier
    messages.success(request, "OCB created and offered to the auction winner.")
    return redirect(f"/pipeline/{lead.id}/")


@require_POST
def retail_create_auction(request, lead_id):
    """DEPRECATED start path. Auctions are now started ONLY by the Retail Head
    (auctions.services.start_auction, via rh_start_auction) — a single creation
    path. This associate route no longer creates anything; it just redirects so an
    old bookmark can't spawn an auction."""
    guard = _require_retail(request)
    if guard:
        return guard
    messages.info(request, "Auctions are now started by the Retail Head.")
    return redirect(f"/crm/retail/lead/{lead_id}/")


# ── OCB ──────────────────────────────────────────────────────────────────────

def retail_ocb_list(request):
    guard = _require_retail(request)
    if guard:
        return guard
    ocbs = (OCBListing.objects.filter(assigned_to=request.user)
            .select_related("vehicle").prefetch_related("offers").order_by("-created_at"))
    from core.margin import base_from_gross
    # Retail surface: show the seller-facing BASE, never the dealer-facing gross.
    rows = [{"ocb": o, "car": _car(o.vehicle), "offers": o.offers.count(),
             "base_price": base_from_gross(o.ocb_price)["base"]} for o in ocbs]
    return render(request, "teams/retail/ocb_list.html", {"rows": rows})


def retail_ocb_create(request):
    """DEPRECATED standalone creator. An OCB is now created ONLY from the lead's
    detail page (retail_lead_create_ocb), guarded to lead.assigned_associate, so an
    OCB can never be orphaned or created by a non-assigned associate. This route
    just redirects an old bookmark to the pipeline so it can't create anything."""
    guard = _require_retail(request)
    if guard:
        return guard
    messages.info(request, "Create an OCB from its lead's detail page (Negotiation stage).")
    return redirect("/pipeline/")


def retail_ocb_detail(request, ocb_id):
    guard = _require_retail(request)
    if guard:
        return guard
    ocb = get_object_or_404(OCBListing.objects.select_related("vehicle", "sales_associate"),
                            id=ocb_id, assigned_to=request.user)

    # Message thread post (same URL)
    if request.method == "POST" and request.POST.get("message"):
        text = request.POST["message"].strip()
        if text:
            OCBMessage.objects.create(ocb_listing=ocb, sender=request.user, message=text)
        return redirect(f"/crm/retail/ocb/{ocb.id}/")

    # NOTE: the Retail Associate does NOT assign the Sales Associate — that is the
    # Sales Head's job (Phase 3 wall). The RA DECLARES (retail_ocb_declare); the OCB
    # then lands in the Sales Head inbox, and the Sales Head assigns the SA.

    # Retail is a masked surface: dealer identity AND gross must never appear here.
    # offer_rows(as_base=True) anonymises dealers (Dealer A/B/C) and de-grosses the
    # price to the seller-facing BASE.
    offers = offer_rows(ocb, reveal_dealer=False, as_base=True)
    thread = ocb.messages.select_related("sender").all()
    # Show whichever SA is set — the Sales Head sets assigned_sales_associate.
    current = ocb.assigned_sales_associate or ocb.sales_associate
    from core.margin import base_from_gross
    S = OCBListing.Status
    # The assigned RA can select a dealer offer & close once one exists — including the
    # winner's accepted offer (winner_accepted). The seller may also confirm the winner
    # (auctions.seller_ocb_respond); either close creates the Deal at Agreement.
    can_close = ocb.status in (S.OPEN, S.WINNER_ACCEPTED, S.WINNER_DECLINED,
                               S.ASSIGNED_TO_SALES, S.DEALERS_CONTACTED)
    awaiting_winner = ocb.status == S.OFFERED_TO_WINNER   # winner hasn't responded yet
    # Deal + agreement status (retail wall: status/signatures only — NO dealer identity,
    # no gross). Lets the RA follow the tail: Agreement -> e-Sign -> payment.
    from deals.models import Deal
    _deal = (Deal.objects.filter(vehicle=ocb.vehicle).select_related("agreement")
             .order_by("-id").first())
    _agr = getattr(_deal, "agreement", None) if _deal else None
    return render(request, "teams/retail/ocb_detail.html", {
        "ocb": ocb, "car": _car(ocb.vehicle), "offers": offers, "thread": thread,
        "ocb_base": base_from_gross(ocb.ocb_price)["base"],   # client price as BASE
        "current_sales": current, "can_close": can_close, "awaiting_winner": awaiting_winner,
        "sales_names": (current.get_full_name() or current.username) if current else "—",
        "deal_status": _deal.get_status_display() if _deal else None,
        "seller_signed": bool(_agr and _agr.seller_signed),
        "dealer_signed": bool(_agr and _agr.dealer_signed),
    })


@require_POST
def retail_ocb_declare(request, ocb_id):
    """The lead's ASSIGNED Retail Associate declares a winner-declined OCB to the
    all-dealers tier. HARD ownership: only assigned_to (the lead's RA) may declare —
    others get 403. Moves it to the Sales Head inbox (ASSIGNED_TO_SALES, no SA)."""
    from django.http import HttpResponseForbidden
    guard = _require_retail(request)
    if guard:
        return guard
    ocb = get_object_or_404(OCBListing.objects.select_related("vehicle"), id=ocb_id)
    if ocb.assigned_to_id != request.user.id:
        return HttpResponseForbidden("Only the assigned Retail Associate can declare this OCB.")
    if ocb.status != OCBListing.Status.WINNER_DECLINED:
        messages.error(request, "This OCB isn't ready to declare yet.")
        return redirect(f"/crm/retail/ocb/{ocb.id}/")
    ocb.status = OCBListing.Status.ASSIGNED_TO_SALES   # declared; awaiting Sales Head assignment
    ocb.save(update_fields=["status", "updated_at"])
    for head in User.objects.filter(role=Role.SALES_HEAD, is_suspended=False):
        notify(head, "task_assigned", title="OCB declared — assign a sales associate",
               body=f"{_car(ocb.vehicle)} — assign it from the OCB inbox.", url="/crm/sales-head/")
    messages.success(request, "OCB declared to the all-dealers tier.")
    return redirect(f"/crm/retail/ocb/{ocb.id}/")


@require_POST
def retail_ocb_select_winner(request, ocb_id):
    guard = _require_retail(request)
    if guard:
        return guard
    ocb = get_object_or_404(OCBListing.objects.select_related("vehicle"),
                            id=ocb_id, assigned_to=request.user)
    S = OCBListing.Status
    # Idempotent — already closed / deal created.
    if ocb.status in (S.ACCEPTED, S.SELLER_ACCEPTED, S.AGREEMENT, S.REJECTED):
        messages.info(request, "This OCB is already closed.")
        return redirect(f"/crm/retail/ocb/{ocb.id}/")
    # Nothing to select yet — the winner hasn't responded.
    if ocb.status == S.OFFERED_TO_WINNER:
        messages.info(request, "Waiting for the auction winner to respond — no offer to select yet.")
        return redirect(f"/crm/retail/ocb/{ocb.id}/")
    offer = get_object_or_404(OCBOffer, id=request.POST.get("offer_id"), ocb_listing=ocb)

    ocb.offers.update(is_selected=False)
    offer.is_selected = True
    offer.save(update_fields=["is_selected"])
    ocb.status = S.SELLER_ACCEPTED   # closed with a chosen offer; a Deal now exists
    ocb.save(update_fields=["status", "updated_at"])

    v = ocb.vehicle
    # Close = Deal from the chosen offer's GROSS (idempotent — one Deal per vehicle),
    # then advance the lead OUT of "OCB processing" to Agreement (rank 110 > OCB's 100;
    # create_deal_from_win only reaches seller_approved at rank 100, a no-op here).
    from deals.services import create_deal_from_win
    from crm.services import transition_lead_for_vehicle
    create_deal_from_win(v, offer.price, offer.dealer, v.seller,
                         assigned_sales=offer.submitted_by)
    transition_lead_for_vehicle(v, "agreement_ready", actor=request.user)
    # create_deal_from_win already notified the dealer + seller. Only ping the Sales
    # Associate when a staff member (not the dealer) logged the offer.
    if offer.submitted_by_id and offer.submitted_by_id != offer.dealer_id:
        notify(offer.submitted_by, "task_assigned", title="Your OCB offer was selected",
               body=f"₹{offer.price:,} for {_car(v)} — deal opened.", url="/crm/sales/ocb/")
    messages.success(request, "Offer selected — OCB closed, deal created, agreement ready.")
    return redirect(f"/crm/retail/ocb/{ocb.id}/")


# ── Task Manager ─────────────────────────────────────────────────────────────

def retail_task_list(request):
    guard = _require_retail(request)
    if guard:
        return guard
    from django.db.models import Q
    tasks = (Task.objects.filter(Q(created_by=request.user) | Q(assigned_to=request.user))
             .select_related("assigned_to", "related_lead__vehicle", "related_ocb__vehicle").distinct())
    columns = []
    for value, label in Task.Status.choices:
        items = [t for t in tasks if t.status == value]
        columns.append({"value": value, "label": label, "count": len(items), "tasks": items})
    return render(request, "teams/retail/task_list.html", {"columns": columns})


def retail_task_create(request):
    guard = _require_retail(request)
    if guard:
        return guard
    assignees = (User.objects.filter(role__in=[Role.SALES, Role.PROCUREMENT], is_suspended=False)
                 .order_by("role", "username"))
    # Leads aren't assigned to the Retail Associate in this workflow (null or the
    # Lead Manager), so an assigned_to filter returns empty — same as the pipeline
    # and OCB views. Show all leads for the optional fallback dropdown.
    leads = Lead.objects.all().select_related("vehicle").order_by("-updated_at")
    ocbs = OCBListing.objects.filter(assigned_to=request.user).select_related("vehicle")

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        assignee_id = request.POST.get("assigned_to") or None
        assignee = (User.objects.filter(id=assignee_id,
                                        role__in=[Role.SALES, Role.PROCUREMENT]).first()
                    if assignee_id else None)
        if not title or not assignee:
            messages.error(request, "Title and a valid assignee are required.")
            return redirect("/crm/retail/tasks/create/")
        priority = request.POST.get("priority")
        if priority not in dict(Task.Priority.choices):
            priority = Task.Priority.MEDIUM
        # OCB is the primary selector. Every OCB is tied to a lead through its
        # vehicle (Lead.vehicle is OneToOne), so when an OCB is chosen we
        # auto-resolve the lead from it and ignore the manual lead field. Only
        # when no OCB is selected do we use the optional Related Lead dropdown.
        # Guard empty strings — an int id lookup on "" raises ValueError.
        ocb_id = request.POST.get("related_ocb") or None
        related_ocb = (OCBListing.objects.filter(id=ocb_id, assigned_to=request.user).first()
                       if ocb_id else None)
        if related_ocb:
            related_lead = Lead.objects.filter(vehicle=related_ocb.vehicle).first()
        else:
            lead_id = request.POST.get("related_lead") or None
            related_lead = Lead.objects.filter(id=lead_id).first() if lead_id else None
        task = Task.objects.create(
            title=title,
            description=(request.POST.get("description") or "").strip(),
            created_by=request.user,
            assigned_to=assignee,
            priority=priority,
            due_date=request.POST.get("due_date") or None,
            related_lead=related_lead,
            related_ocb=related_ocb,
        )
        notify(assignee, "task_assigned", title="New task assigned",
               body=task.title, url="/")
        messages.success(request, "Task created.")
        return redirect("/crm/retail/tasks/")

    # Each OCB carries its auto-resolved lead label so the form can show
    # "Linked lead: …" when an OCB is picked.
    ocb_rows = []
    for o in ocbs:
        olead = Lead.objects.filter(vehicle=o.vehicle).select_related("seller").first()
        if olead:
            who = (olead.seller.get_full_name() or olead.seller.username) if olead.seller else ""
            lead_label = f"#{olead.id} · {_car(o.vehicle)}" + (f" · {who}" if who else "")
        else:
            lead_label = ""
        ocb_rows.append({"id": o.id, "label": f"{_car(o.vehicle)} (₹{o.ocb_price})", "lead": lead_label})

    return render(request, "teams/retail/task_create.html", {
        "assignees": assignees,
        "leads": [{"id": l.id, "label": f"{_car(l.vehicle)}" if l.vehicle else f"Lead #{l.id}"} for l in leads],
        "ocbs": ocb_rows,
        "priorities": Task.Priority.choices,
    })


def retail_task_detail(request, task_id):
    guard = _require_retail(request)
    if guard:
        return guard
    from django.db.models import Q
    task = get_object_or_404(
        Task.objects.filter(Q(created_by=request.user) | Q(assigned_to=request.user))
        .select_related("assigned_to", "created_by", "related_lead__vehicle", "related_ocb__vehicle"),
        id=task_id)
    # Retail wall: if this task links an OCB, show its price as the seller-facing
    # BASE, never the dealer-facing gross.
    ocb_base = None
    if task.related_ocb and task.related_ocb.ocb_price:
        from core.margin import base_from_gross
        ocb_base = base_from_gross(task.related_ocb.ocb_price)["base"]
    return render(request, "teams/retail/task_detail.html", {
        "task": task, "statuses": Task.Status.choices, "ocb_base": ocb_base,
    })


@require_POST
def retail_task_status_update(request, task_id):
    guard = _require_retail(request)
    if guard:
        return guard
    from django.db.models import Q
    task = get_object_or_404(
        Task.objects.filter(Q(created_by=request.user) | Q(assigned_to=request.user)), id=task_id)
    new_status = request.POST.get("new_status")
    if new_status in dict(Task.Status.choices):
        task.status = new_status
        task.save(update_fields=["status", "updated_at"])
        messages.success(request, "Status updated.")
    else:
        messages.error(request, "Invalid status.")
    return redirect(f"/crm/retail/tasks/{task.id}/")
