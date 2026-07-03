from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from .models import Ticket, TicketMessage


@login_required(login_url="/auth/login/")
def support_home(request):
    open_count = (Ticket.objects.filter(owner=request.user)
                  .exclude(status=Ticket.Status.RESOLVED).count())
    return render(request, "www/support/home.html", {"open_count": open_count})


@login_required(login_url="/auth/login/")
def support_faq(request):
    return render(request, "www/support/faq.html", {})


@login_required(login_url="/auth/login/")
def ticket_new(request):
    error = None
    subject = category = body = ""
    if request.method == "POST":
        subject  = (request.POST.get("subject") or "").strip()
        category = (request.POST.get("category") or "").strip()
        body     = (request.POST.get("body") or "").strip()
        if not subject or not body:
            error = "Add a subject and a short description so we can help."
        else:
            if category not in dict(Ticket.Category.choices):
                category = Ticket.Category.OTHER
            ticket = Ticket.objects.create(
                owner=request.user, subject=subject[:200],
                category=category, body=body,
            )
            TicketMessage.objects.create(ticket=ticket, author=request.user, body=body)
            return redirect("ticket_detail", pk=ticket.pk)
    return render(request, "www/support/ticket_new.html", {
        "error": error, "categories": Ticket.Category.choices,
        "subject": subject, "category_sel": category, "body": body,
    })


@login_required(login_url="/auth/login/")
def my_tickets(request):
    tickets = Ticket.objects.filter(owner=request.user)
    return render(request, "www/support/tickets.html", {"tickets": tickets})


@login_required(login_url="/auth/login/")
def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk, owner=request.user)
    if request.method == "POST":
        body = (request.POST.get("body") or "").strip()
        if body:
            TicketMessage.objects.create(ticket=ticket, author=request.user, body=body)
            if ticket.status == Ticket.Status.RESOLVED:
                ticket.status = Ticket.Status.OPEN
                ticket.save(update_fields=["status", "updated_at"])
            else:
                ticket.save(update_fields=["updated_at"])
        return redirect("ticket_detail", pk=ticket.pk)
    return render(request, "www/support/ticket_detail.html", {
        "ticket": ticket,
        "thread": ticket.messages.select_related("author"),
    })
