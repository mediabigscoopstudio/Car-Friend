from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from accounts.decorators import admin_required
from accounts.dealer_docs import DEALER_REQUIRED_DOCS
from accounts.forms import DealerVerificationForm, validate_document
from core.models import log
from kyc.models import KYCVerification
from notifications.services import notify
from .models import (
    User, Role, DealerProfile,
    DealerVerification, DealerDocument,
    dealer_can_bid, latest_dealer_verification,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_dashboard_url(user):
    if user.role == Role.SELLER:
        return "/auth/seller/dashboard/"
    elif user.role == Role.DEALER:
        return "/auth/dealer/dashboard/"
    elif user.role == Role.LEAD_MANAGER:
        return "/crm/lead-manager/dashboard/"
    elif user.role == Role.RETAIL_HEAD:
        return "/crm/retail-head/"
    elif user.role == Role.SALES_HEAD:
        return "/crm/sales-head/"
    elif user.role == Role.RETAIL:
        return "/crm/retail/dashboard/"
    elif user.role == Role.SALES:
        return "/crm/sales/dashboard/"
    elif user.role == Role.INSPECTOR:
        return "/crm/inspection/dashboard/"
    elif user.role == Role.PROCUREMENT:
        return "/crm/procurement/dashboard/"
    elif user.is_internal:
        return "/"   # internal staff: master/teams dashboard handles routing
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
                "inspector": "/inspector",
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
    next_url = request.GET.get("next", "").strip()
    error = None
    if request.method == "POST":
        email    = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        next_url = request.POST.get("next", "").strip()
        user = authenticate(request, username=email, password=password)
        if user is None:
            # fallback: try looking up by email field (covers allauth-created accounts)
            try:
                u = User.objects.get(email__iexact=email)
                user = authenticate(request, username=u.username, password=password)
            except User.DoesNotExist:
                pass
        if user is not None and not user.is_suspended:
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            dest = next_url if next_url and next_url.startswith("/") else get_dashboard_url(user)
            return redirect(dest)
        else:
            error = "The email or password you entered is incorrect."
    # Internal hosts (teams/master/inspection) get a clean staff login card with
    # no public www header/footer; the www host keeps the public login.
    host_label = request.get_host().split(":")[0].split(".")[0].lower()
    template = "auth/team_login.html" if host_label in ("teams", "master", "inspection") else "www/auth/login.html"
    return render(request, template, {
        "error": error, "next": next_url,
        "intended_role": request.session.get("intended_role", ""),  # dealer/seller heading
    })


def register_page(request):
    if request.user.is_authenticated:
        return redirect(get_dashboard_url(request.user))
    next_url = request.GET.get("next", "").strip()
    error = None
    if request.method == "POST":
        next_url = request.POST.get("next", "").strip()
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
            dest = next_url if next_url and next_url.startswith("/") else get_dashboard_url(user)
            return redirect(dest)
    return render(request, "www/auth/register.html", {"error": error, "next": next_url})


def logout_page(request):
    logout(request)
    request.session.flush()      # clear active_role/intended_role + any stale session
    return redirect("/")


def role_redirect(request):
    if not request.user.is_authenticated:
        return redirect("/auth/login/")
    u = request.user
    intended = request.session.pop("intended_role", None)
    # Staff / internal roles keep their existing routing untouched — never demoted.
    if u.role not in (Role.SELLER, Role.DEALER):
        return redirect(get_dashboard_url(u))
    # Public user: a pre-login 'Join as Dealer' / 'Sell your car' intent locks the
    # role for this account. To use the other role they log out and pick the
    # other entry (hard wall — no in-app switch).
    if intended in ("seller", "dealer"):
        u.role = Role.DEALER if intended == "dealer" else Role.SELLER
        u.save(update_fields=["role"])
    return redirect(get_dashboard_url(u))


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


def login_as_dealer(request):
    """Public 'Join as Dealer' CTA: lock dealer intent, then go to the login
    page (Google or email). role_redirect applies the role after sign-in."""
    request.session["intended_role"] = "dealer"
    if request.user.is_authenticated:
        return redirect("role_redirect")
    return redirect("/auth/login/?next=/auth/role-redirect/")


def login_as_seller(request):
    """Public 'Sell your car' CTA: lock seller intent, then go to the login page."""
    request.session["intended_role"] = "seller"
    if request.user.is_authenticated:
        return redirect("role_redirect")
    return redirect("/auth/login/?next=/auth/role-redirect/")


# ── Dashboards ────────────────────────────────────────────────────────────────

def _safe_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


@login_required(login_url="/auth/login/")
def dealer_onboard(request):
    """Dealer verification: business details + required document uploads.

    Creates a DealerVerification (pending) that a super admin approves. The
    dealer cannot bid until approved. Re-submittable after a rejection.
    """
    latest = latest_dealer_verification(request.user)
    # A pending or approved submission already exists — go to the dashboard.
    if latest and latest.status in (DealerVerification.Status.PENDING, DealerVerification.Status.APPROVED):
        return redirect("/auth/dealer/dashboard/")

    error = None
    if request.method == "POST":
        form  = DealerVerificationForm(request.POST)
        city  = request.POST.get("city", "").strip()
        phone = request.POST.get("phone", "").strip()
        brand_interest = request.POST.get("brand_interest", "").strip()

        # Validate the required documents.
        doc_files, doc_error = {}, None
        for key, label in DEALER_REQUIRED_DOCS:
            f = request.FILES.get(f"doc_{key}")
            err = validate_document(f)
            if err:
                doc_error = f"{label}: {err}"
                break
            doc_files[key] = f

        if not form.is_valid():
            error = next(iter(form.errors.values()))[0]
        elif not city:
            error = "City is required."
        elif doc_error:
            error = doc_error
        else:
            request.user.role = Role.DEALER
            request.user.city = city
            if phone:
                request.user.phone = phone
            request.user.save(update_fields=["role", "city", "phone"])
            DealerProfile.objects.update_or_create(
                user=request.user,
                defaults={
                    "dealership_name": form.cleaned_data["business_name"],
                    "gstin":           form.cleaned_data["gstin"],
                    "city":            city,
                    "budget_min":      _safe_int(request.POST.get("budget_min")),
                    "budget_max":      _safe_int(request.POST.get("budget_max")),
                    "brand_interest":  brand_interest,
                },
            )
            verification = DealerVerification.objects.create(
                dealer=request.user,
                business_name=form.cleaned_data["business_name"],
                gstin=form.cleaned_data["gstin"],
                status=DealerVerification.Status.PENDING,
            )
            for key, f in doc_files.items():
                DealerDocument.objects.create(verification=verification, doc_type=key, file=f)
            log(request.user, "dealer.verification.submit", verification, request)
            notify(request.user, "dealer_verification",
                   title="Verification submitted",
                   body="Your documents are under review. We'll notify you once approved.")
            return redirect("/auth/dealer/dashboard/")

    return render(request, "www/dashboard/dealer_onboard.html", {
        "error": error,
        "required_docs": DEALER_REQUIRED_DOCS,
        "rejected": bool(latest and latest.status == DealerVerification.Status.REJECTED),
        "reject_reason": latest.reject_reason if latest else "",
    })


@login_required(login_url="/auth/login/")
def switch_role(request):
    """POST-only: toggle between seller and dealer roles."""
    if request.method != "POST":
        return redirect(get_dashboard_url(request.user))
    target = request.POST.get("target_role", "")
    if target == Role.DEALER:
        # Need a DealerProfile first
        if not hasattr(request.user, "dealer_profile"):
            return redirect("/auth/dealer/onboard/")
        request.user.role = Role.DEALER
        request.user.save(update_fields=["role"])
        return redirect("/auth/dealer/dashboard/")
    elif target == Role.SELLER:
        request.user.role = Role.SELLER
        request.user.save(update_fields=["role"])
        return redirect("/auth/seller/dashboard/")
    return redirect(get_dashboard_url(request.user))


def _seller_kyc_state(user):
    def st(kind):
        rec = KYCVerification.objects.filter(subject=user, kind=kind).order_by("-created_at").first()
        return rec.status if rec else None
    pan, aad = st("pan"), st("aadhaar")
    if user.is_kyc_done:
        return "verified"
    if pan == "rejected" or aad == "rejected":
        return "failed"
    return "pending"


@login_required(login_url="/auth/login/")
def seller_dashboard(request):
    # Sellers see their dashboard; admins may open it too (preview). Dealers and
    # CRM staff each have their own dashboard, so send them there instead of
    # rendering the seller page.
    if not request.user.is_seller and not request.user.is_admin:
        return redirect(get_dashboard_url(request.user))

    # Close any auctions whose timer has expired so they surface below.
    from auctions.utils import auto_close_expired_auctions
    auto_close_expired_auctions()

    # Post-auction decisions: closed/ended auctions on this seller's cars, with
    # any decision already made + the linked OCB status (read-only display of the
    # real CRM pipeline). Live auctions are not shown here.
    from auctions.models import Auction, OCBListing
    pending_decisions = []
    for a in (Auction.objects.filter(vehicle__seller=request.user,
                                      status__in=["closed", "reauction", "completed"])
              .select_related("vehicle").order_by("-end_at")):
        hb = a.highest_bid
        ocb = OCBListing.objects.filter(auction=a).order_by("-id").first()
        pending_decisions.append({
            "auction":       a,
            "vehicle":       a.vehicle,
            "decision":      a.seller_decisions.order_by("-id").first(),
            "highest_bid":   hb,
            "highest_fmt":   f"{hb.amount:,}" if hb else None,
            "counter_fmt":   None,
            "bid_count":     a.bids.filter(is_voided=False).count(),
            "ocb":           ocb,
            "ocb_status":    ocb.get_status_display() if ocb else None,
            "ocb_signable":  bool(ocb and ocb.status in ("winner_accepted", "seller_accepted", "agreement")),
        })
    for pd in pending_decisions:
        d = pd["decision"]
        if d and d.counter_price:
            pd["counter_fmt"] = f"{d.counter_price:,}"

    return render(request, "www/dashboard/seller.html", {
        "kyc_status": _seller_kyc_state(request.user),
        "pending_decisions": pending_decisions,
    })


@login_required(login_url="/auth/login/")
def dealer_dashboard(request):
    if not request.user.is_dealer:
        return redirect(get_dashboard_url(request.user))
    latest = latest_dealer_verification(request.user)
    from django.utils import timezone
    from auctions.models import Auction, Bid
    from auctions.utils import auto_close_expired_auctions
    auto_close_expired_auctions()
    now = timezone.now()
    live_count = Auction.objects.filter(status="live", start_at__lte=now, end_at__gt=now).count()
    my_active_bids = (Bid.objects.filter(dealer=request.user, is_voided=False,
                                         auction__status="live", auction__end_at__gt=now)
                      .values("auction").distinct().count())

    # Bid history — one row per auction this dealer bid on, newest first, with
    # won/lost outcome. vehicle make/model/year only (no PII), as shown in-room.
    bid_history, seen = [], set()
    for bid in (Bid.objects.filter(dealer=request.user)
                .select_related("auction", "auction__vehicle").order_by("-created_at")):
        a = bid.auction
        if a.id in seen:
            continue
        seen.add(a.id)
        highest = a.bids.filter(is_voided=False).order_by("-amount").first()
        my_highest = a.bids.filter(dealer=request.user, is_voided=False).order_by("-amount").first()
        is_live = a.status == "live" and a.end_at > now
        is_closed = a.status in ("closed", "completed", "reauction")
        i_won = bool(is_closed and highest and my_highest and highest.id == my_highest.id)
        bid_history.append({
            "auction": a, "vehicle": a.vehicle,
            "my_amount": my_highest.amount if my_highest else None,
            "top_amount": highest.amount if highest else None,
            "is_live": is_live, "i_won": i_won, "i_lost": is_closed and not i_won,
        })
        if len(bid_history) >= 25:
            break

    return render(request, "www/dashboard/dealer.html", {
        "verification_status": latest.status if latest else None,  # None/pending/approved/rejected
        "reject_reason": latest.reject_reason if latest else "",
        "can_bid": dealer_can_bid(request.user),
        "live_count": live_count,
        "my_active_bids": my_active_bids,
        "bid_history": bid_history,
    })


# ── Admin: dealer verification approval queue (super-admin) ──────────────────

@admin_required
def dealer_verifications(request):
    """Pending dealer verification submissions for admin review."""
    pending = (DealerVerification.objects
               .filter(status=DealerVerification.Status.PENDING)
               .select_related("dealer").prefetch_related("documents"))
    return render(request, "master/dealer_verifications.html", {
        "active": "dealer_verifications",
        "records": pending,
    })


@admin_required
def dealer_verification_detail(request, id):
    rec = get_object_or_404(
        DealerVerification.objects.select_related("dealer").prefetch_related("documents"), id=id)
    return render(request, "master/dealer_verification_detail.html", {
        "active": "dealer_verifications",
        "rec": rec,
    })


@admin_required
def dealer_verification_decide(request, id):
    if request.method != "POST":
        return redirect("/dealer_verifications")
    rec = get_object_or_404(DealerVerification, id=id)
    decision = request.POST.get("decision")

    if decision == "approve":
        rec.status = DealerVerification.Status.APPROVED
        rec.reject_reason = ""
        rec.reviewed_by = request.user
        rec.reviewed_at = timezone.now()
        rec.save()
        # Ensure the dealer profile is enabled for bidding.
        DealerProfile.objects.filter(user=rec.dealer).update(status="Enabled", is_banned=False)
        log(request.user, "dealer.verification.approve", rec, request)
        notify(rec.dealer, "dealer_verification",
               title="Verification approved",
               body="Your dealer account is verified. You can now bid in auctions.")
    elif decision == "reject":
        reason = (request.POST.get("reason") or "").strip()
        if not reason:
            messages.error(request, "A reason is required to reject.")
            return redirect(f"/dealer_verifications/{rec.id}/")
        rec.status = DealerVerification.Status.REJECTED
        rec.reject_reason = reason
        rec.reviewed_by = request.user
        rec.reviewed_at = timezone.now()
        rec.save()
        log(request.user, "dealer.verification.reject", rec, request, reason=reason)
        notify(rec.dealer, "dealer_verification",
               title="Verification needs changes",
               body=reason)
    return redirect("/dealer_verifications")


@admin_required
def dealer_document_download(request, doc_id):
    """Stream a private dealer document — admin only, never publicly served."""
    doc = get_object_or_404(DealerDocument, id=doc_id)
    try:
        fh = doc.file.open("rb")
    except (FileNotFoundError, ValueError):
        raise Http404("Document not available.")
    log(request.user, "dealer.document.view", doc, request)
    return FileResponse(fh, as_attachment=False, filename=f"{doc.doc_type}_{doc.id}")
