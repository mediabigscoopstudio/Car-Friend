from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Notification


@login_required(login_url="/auth/login/")
def notifications_inbox(request):
    notes = Notification.objects.filter(recipient=request.user)[:100]
    unread = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return render(request, "www/notifications.html", {"notes": notes, "unread": unread})


@login_required(login_url="/auth/login/")
def notification_open(request, pk):
    note = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not note.is_read:
        note.is_read = True
        note.save(update_fields=["is_read"])
    if note.url:
        return redirect(note.url)
    return redirect("notifications_inbox")


@login_required(login_url="/auth/login/")
@require_POST
def notifications_read_all(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect("notifications_inbox")
