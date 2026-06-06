from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404

from accounts.decorators import admin_required
from core.models import log
from .models import User, Role


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_dashboard_url(user):
    if user.role == Role.SELLER:
        return "/auth/seller/dashboard/"
    elif user.role == Role.DEALER:
        return "/auth/dealer/dashboard/"
    elif user.is_internal:
        return "/"   # internal staff: master dashboard handles routing
    return "/"


# ── Master-app views (used by urls_master.py) ─────────────────────────────────

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


# ── Public auth views ─────────────────────────────────────────────────────────

def login_page(request):
    if request.user.is_authenticated:
        return redirect(get_dashboard_url(request.user))
    error = None
    if request.method == "POST":
        email    = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        # allauth uses email as username when ACCOUNT_USERNAME_REQUIRED=False
        user = authenticate(request, username=email, password=password)
        if user and not user.is_suspended:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return redirect(get_dashboard_url(user))
        else:
            error = "The email or password you entered is incorrect."
    return render(request, "www/auth/login.html", {"error": error})


def register_page(request):
    if request.user.is_authenticated:
        return redirect(get_dashboard_url(request.user))
    error = None
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()
        last_name  = request.POST.get("last_name", "").strip()
        email      = request.POST.get("email", "").strip().lower()
        phone      = request.POST.get("phone", "").strip()
        password1  = request.POST.get("password1", "")
        password2  = request.POST.get("password2", "")
        role       = request.POST.get("role", Role.SELLER)

        if User.objects.filter(email=email).exists():
            error = "An account with this email already exists. Please log in instead."
        elif password1 != password2:
            error = "Passwords do not match. Please try again."
        elif len(password1) < 8:
            error = "Password must be at least 8 characters long."
        elif role not in [Role.SELLER, Role.DEALER]:
            error = "Please select a valid account type."
        else:
            user = User.objects.create_user(
                username   = email,
                email      = email,
                password   = password1,
                first_name = first_name,
                last_name  = last_name,
                phone      = phone,
                role       = role,
            )
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            messages.success(request, f"Welcome to CarFriend, {first_name}!")
            return redirect(get_dashboard_url(user))
    return render(request, "www/auth/register.html", {"error": error})


def logout_page(request):
    logout(request)
    return redirect("/")


def role_redirect(request):
    if not request.user.is_authenticated:
        return redirect("/auth/login/")
    return redirect(get_dashboard_url(request.user))


def set_role(request):
    if not request.user.is_authenticated:
        return redirect("/auth/login/")
    if request.method == "POST":
        role = request.POST.get("role", Role.SELLER)
        if role in [Role.SELLER, Role.DEALER]:
            request.user.role = role
            request.user.save(update_fields=["role"])
        return redirect(get_dashboard_url(request.user))
    return render(request, "www/auth/set_role.html")


# ── Dashboards ────────────────────────────────────────────────────────────────

@login_required(login_url="/auth/login/")
def seller_dashboard(request):
    if not request.user.is_seller:
        return redirect(get_dashboard_url(request.user))
    return render(request, "www/dashboard/seller.html")


@login_required(login_url="/auth/login/")
def dealer_dashboard(request):
    if not request.user.is_dealer:
        return redirect(get_dashboard_url(request.user))
    return render(request, "www/dashboard/dealer.html")
