from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect, get_object_or_404

from accounts.decorators import admin_required
from core.models import log
from .models import User, Role


def login_view(request):
    if request.method == "POST":
        u = authenticate(
            request,
            username=request.POST["username"],
            password=request.POST["password"],
        )
        if u and not u.is_suspended:
            login(request, u)
            dest = {
                "admin":     "/",
                "retail":    "/pipeline",
                "sales":     "/dealers",
                "inspector": "/visits",
            }.get(u.role, "/")
            return redirect(dest)
        return render(request, "base/signin.html", {"error": "Invalid credentials"})
    return render(request, "base/signin.html")


def logout_view(request):
    logout(request)
    return redirect("/login_view")


@admin_required
def users(request):
    return render(
        request,
        "master/users.html",
        {"active": "users", "members": User.objects.filter(is_internal=True), "roles": Role.choices},
    )


@admin_required
def add_user(request):
    if request.method == "POST":
        u = User.objects.create_user(
            username=request.POST["username"],
            email=request.POST.get("email", ""),
            password=request.POST["password"],
            role=request.POST["role"],
            phone=request.POST.get("phone", ""),
            is_internal=True,
            first_name=request.POST.get("first_name", ""),
        )
        log(request.user, "user.create", u, request, role=u.role)
        return redirect("/users")
    return render(request, "master/add_user.html", {"active": "users", "roles": Role.choices})


@admin_required
def suspend_user(request, id):
    u = get_object_or_404(User, id=id)
    u.is_suspended = not u.is_suspended
    u.save()
    log(request.user, "user.suspend", u, request, suspended=u.is_suspended)
    return redirect("/users")
