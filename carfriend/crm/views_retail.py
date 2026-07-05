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
from auctions.models import OCBListing, OCBMessage, OCBOffer
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
    rows = [{"ocb": o, "car": _car(o.vehicle), "offers": o.offers.count()} for o in ocbs]
    return render(request, "teams/retail/ocb_list.html", {"rows": rows})


def retail_ocb_create(request):
    guard = _require_retail(request)
    if guard:
        return guard
    # Leads are not assigned to the Retail Associate in the current workflow
    # (assigned_to is null or the Lead Manager) — same reason the pipeline view
    # shows all leads — so do NOT filter by assigned_to or the dropdown is empty.
    leads = (Lead.objects.filter(stage__in=[Lead.STAGE_NEGOTIATION, Lead.STAGE_AUCTION])
             .select_related("vehicle").order_by("-updated_at"))
    sales = User.objects.filter(role=Role.SALES, is_suspended=False).order_by("username")

    if request.method == "POST":
        lead = get_object_or_404(Lead, id=request.POST.get("lead_id"))
        try:
            price = int(request.POST.get("ocb_price", "0"))
        except (TypeError, ValueError):
            price = 0
        if price <= 0:
            messages.error(request, "Enter a valid client-suitable price.")
            return redirect("/crm/retail/ocb/create/")
        # Resolve the chosen Sales Associate first so we can store the link on
        # the OCB (sales_associate) — this is what scopes the Sales OCB board.
        sales_user = User.objects.filter(id=request.POST.get("sales_id"), role=Role.SALES).first()
        ocb = OCBListing.objects.create(
            vehicle=lead.vehicle, ocb_price=price, assigned_to=request.user,
            sales_associate=sales_user, status=OCBListing.Status.OPEN)
        notes = (request.POST.get("notes") or "").strip()
        if notes:
            OCBMessage.objects.create(ocb_listing=ocb, sender=request.user,
                                      message=f"Instructions for Sales: {notes}")
        # Winner-first lifecycle: offer to the auction winner; only on decline
        # does the Sales Head route it to a sales associate (assumption B).
        offer_to_winner(ocb, actor=request.user)
        messages.success(request, "OCB created and offered to the auction winner.")
        return redirect(f"/crm/retail/ocb/{ocb.id}/")

    try:
        preselect = int(request.GET.get("lead", "") or 0)
    except (TypeError, ValueError):
        preselect = 0
    return render(request, "teams/retail/ocb_create.html", {
        "leads": [{"id": l.id, "label": f"{_car(l.vehicle)} · {l.vehicle.plate_number}" if l.vehicle else l.id,
                   "price": l.vehicle.expected_price if l.vehicle else ""} for l in leads],
        "sales": sales,
        "preselect": preselect,
    })


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

    # Retail is a masked surface: dealer identity must never be exposed here.
    offers = offer_rows(ocb, reveal_dealer=False)
    thread = ocb.messages.select_related("sender").all()
    # Show whichever SA is set — the Sales Head sets assigned_sales_associate.
    current = ocb.assigned_sales_associate or ocb.sales_associate
    return render(request, "teams/retail/ocb_detail.html", {
        "ocb": ocb, "car": _car(ocb.vehicle), "offers": offers, "thread": thread,
        "current_sales": current,
        "sales_names": (current.get_full_name() or current.username) if current else "—",
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
    if ocb.status == OCBListing.Status.ACCEPTED:
        messages.error(request, "This OCB is already closed.")
        return redirect(f"/crm/retail/ocb/{ocb.id}/")
    offer = get_object_or_404(OCBOffer, id=request.POST.get("offer_id"), ocb_listing=ocb)

    ocb.offers.update(is_selected=False)
    offer.is_selected = True
    offer.save(update_fields=["is_selected"])
    ocb.status = OCBListing.Status.ACCEPTED
    ocb.save(update_fields=["status"])

    v = ocb.vehicle
    # Seller-accepted OCB offer -> shared Deal creation (grossed money split).
    from deals.services import create_deal_from_win
    create_deal_from_win(v, offer.price, offer.dealer, v.seller,
                         assigned_sales=offer.submitted_by)
    if offer.submitted_by:
        notify(offer.submitted_by, "task_assigned", title="Your OCB offer was selected",
               body=f"₹{offer.price:,} for {_car(v)} — deal opened.", url="/ocb/sales/")
    messages.success(request, "Winning offer selected — OCB closed and deal opened.")
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
    return render(request, "teams/retail/task_detail.html", {
        "task": task, "statuses": Task.Status.choices,
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
