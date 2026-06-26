"""Sales Associate (teams host) — OCB board (assigned-only), restricted Task
Manager, OCB dealer offers + Retail<->Sales chat.

Strict scope: a Sales Associate only ever sees OCBs whose sales_associate is
them, and tasks assigned to them. They submit dealer offers and chat on an OCB,
and add/update their own task notes — but they cannot edit OCB data, select an
OCB winner, change a task status, or create tasks (all Retail-only).
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import DealerProfile, Role, User
from auctions.models import OCBListing, OCBMessage, OCBOffer
from crm.models import Task, TaskNote
from notifications.services import notify


def _require_sales(request):
    if not request.user.is_authenticated:
        return redirect("/auth/login/")
    if request.user.role != User.ROLE_SALES and not request.user.is_superuser:
        from accounts.views import get_dashboard_url
        return redirect(get_dashboard_url(request.user))
    return None


def _car(vehicle):
    if not vehicle:
        return "—"
    return f"{vehicle.make} {vehicle.model} {vehicle.year}".strip()


# ── OCB (assigned to me only) ────────────────────────────────────────────────

def sales_ocb_list(request):
    guard = _require_sales(request)
    if guard:
        return guard
    from django.db.models import Q
    # OCBs assigned the legacy way (retail-set sales_associate) OR via the Sales
    # Head (assigned_sales_associate) both belong to this associate's board.
    ocbs = (OCBListing.objects.filter(Q(sales_associate=request.user)
                                      | Q(assigned_sales_associate=request.user))
            .select_related("vehicle").prefetch_related("offers").distinct().order_by("-created_at"))
    rows = [{"ocb": o, "car": _car(o.vehicle),
             "my_offers": o.offers.filter(submitted_by=request.user).count()} for o in ocbs]
    return render(request, "teams/sales/ocb_list.html", {"rows": rows})


def sales_ocb_detail(request, ocb_id):
    guard = _require_sales(request)
    if guard:
        return guard
    ocb = get_object_or_404(OCBListing.objects.select_related("vehicle"), id=ocb_id)
    # Only the assigned Sales Associate (retail-set or Sales-Head-set) or a
    # superuser may view/act.
    if (ocb.sales_associate_id != request.user.id
            and ocb.assigned_sales_associate_id != request.user.id
            and not request.user.is_superuser):
        messages.error(request, "This OCB is not assigned to you.")
        return redirect("/crm/sales/ocb/")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "message":
            text = (request.POST.get("message") or "").strip()
            if text:
                OCBMessage.objects.create(ocb_listing=ocb, sender=request.user, message=text)
                if ocb.assigned_to and ocb.assigned_to != request.user:
                    notify(ocb.assigned_to, "task_assigned", title="New OCB message",
                           body=text[:80], url=f"/crm/retail/ocb/{ocb.id}/")
        elif action == "offer":
            # Accept any user that has a DealerProfile (not gated on role flag).
            dealer = User.objects.filter(id=request.POST.get("dealer_id"),
                                         dealer_profile__isnull=False).first()
            try:
                price = int(request.POST.get("price", "0"))
            except (TypeError, ValueError):
                price = 0
            if not dealer or price <= 0:
                messages.error(request, "Pick a dealer and enter a valid offer price.")
            else:
                OCBOffer.objects.create(
                    ocb_listing=ocb, dealer=dealer, price=price,
                    notes=(request.POST.get("notes") or "").strip(), submitted_by=request.user)
                # First dealer offer moves the OCB into "dealers contacted".
                if ocb.status == OCBListing.Status.ASSIGNED_TO_SALES:
                    ocb.status = OCBListing.Status.DEALERS_CONTACTED
                    ocb.save(update_fields=["status", "updated_at"])
                if ocb.assigned_to and ocb.assigned_to != request.user:
                    notify(ocb.assigned_to, "task_assigned", title="New dealer offer",
                           body=f"₹{price:,} for {_car(ocb.vehicle)}", url=f"/crm/retail/ocb/{ocb.id}/")
                messages.success(request, "Offer submitted.")
        return redirect(f"/crm/sales/ocb/{ocb.id}/")

    offers = ocb.offers.select_related("dealer").filter(submitted_by=request.user)
    thread = ocb.messages.select_related("sender").all()
    instructions = ocb.messages.filter(message__startswith="Instructions for Sales:").first()
    # Source the dropdown from DealerProfile (every dealer in the network), NOT
    # User.role==dealer — some dealer accounts don't carry that role flag, which
    # was hiding them. Label: "<Dealership Name> — <City> (<Contact Person>)".
    dealers = []
    for prof in DealerProfile.objects.select_related("user").order_by("dealership_name"):
        u = prof.user
        contact = u.get_full_name() or u.username
        label = prof.dealership_name or contact
        if prof.city:
            label += f" — {prof.city}"
        if prof.dealership_name and contact:
            label += f" ({contact})"
        dealers.append({"id": u.id, "label": label})
    return render(request, "teams/sales/ocb_detail.html", {
        "ocb": ocb, "car": _car(ocb.vehicle), "offers": offers, "thread": thread,
        "dealers": dealers, "instructions": instructions,
    })


# ── Task Manager (assigned to me only; status read-only; notes editable) ──────

def sales_task_list(request):
    guard = _require_sales(request)
    if guard:
        return guard
    tasks = (Task.objects.filter(assigned_to=request.user)
             .select_related("related_ocb__vehicle", "related_lead__vehicle"))
    columns = []
    for value, label in Task.Status.choices:
        items = [t for t in tasks if t.status == value]
        columns.append({"value": value, "label": label, "count": len(items), "tasks": items})
    return render(request, "teams/sales/task_list.html", {"columns": columns})


def sales_task_detail(request, task_id):
    guard = _require_sales(request)
    if guard:
        return guard
    task = get_object_or_404(
        Task.objects.select_related("created_by", "assigned_to",
                                    "related_ocb__vehicle", "related_lead__vehicle"),
        id=task_id)
    if task.assigned_to_id != request.user.id and not request.user.is_superuser:
        messages.error(request, "This task is not assigned to you.")
        return redirect("/crm/sales/tasks/")
    notes = task.notes.select_related("author").all()
    return render(request, "teams/sales/task_detail.html", {"task": task, "notes": notes})


@require_POST
def sales_task_add_note(request, task_id):
    guard = _require_sales(request)
    if guard:
        return guard
    task = get_object_or_404(Task, id=task_id)
    if task.assigned_to_id != request.user.id and not request.user.is_superuser:
        messages.error(request, "This task is not assigned to you.")
        return redirect("/crm/sales/tasks/")
    text = (request.POST.get("note") or "").strip()
    note_id = request.POST.get("note_id")
    if text:
        if note_id:
            # Authors may edit only their own notes.
            existing = TaskNote.objects.filter(id=note_id, task=task, author=request.user).first()
            if existing:
                existing.note = text
                existing.save(update_fields=["note", "updated_at"])
                messages.success(request, "Note updated.")
            else:
                messages.error(request, "You can only edit your own notes.")
        else:
            TaskNote.objects.create(task=task, author=request.user, note=text)
            messages.success(request, "Note added.")
    return redirect(f"/crm/sales/tasks/{task.id}/")
