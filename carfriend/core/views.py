from django.shortcuts import render, redirect, get_object_or_404

from accounts.decorators import admin_required
from accounts.models import User, Role
from .models import FeatureToggle, AuditLog, log
from inspections.models import InspectionReport, InspectionVisit
from kyc.models import KYCVerification
from payments.models import Payment
from auctions.models import Auction
from crm.models import Lead


def coming_soon(request, host_label=""):
    return render(request, "coming_soon.html", {"host_label": host_label})


def index(request):
    return render(
        request,
        "app_index.html",
        {
            "title": "Core",
            "does": "provides shared base models, the feature-toggle engine, audit "
            "logging, and S3/media helpers used across the platform.",
        },
    )


@admin_required
def master_dashboard(request):
    from deals.models import Deal

    ctx = {
        "deals_closed": Deal.objects.filter(status="closed").count(),
        "funnel": {
            "leads":       Lead.objects.count(),
            "inspections": InspectionVisit.objects.filter(status="approved").count(),
            "auctions":    Auction.objects.count(),
            "deals":       Deal.objects.count(),
        },
        "pending_reviews": (
            InspectionReport.objects.filter(visit__status="submitted").count()
            + KYCVerification.objects.filter(status="pending").count()
            + Payment.objects.filter(status="pending").count()
        ),
        "team": User.objects.filter(is_internal=True),
    }
    return render(request, "master/dashboard.html", ctx)


@admin_required
def feature_toggles(request):
    if request.method == "POST":
        ft = get_object_or_404(FeatureToggle, pk=request.POST["id"])
        ft.enabled = not ft.enabled
        ft.save()
        log(request.user, "feature.toggle", ft, request, enabled=ft.enabled)
        return redirect("/features")
    return render(request, "master/features.html", {"toggles": FeatureToggle.objects.all()})


@admin_required
def audit_log_view(request):
    return render(request, "master/audit.html", {"logs": AuditLog.objects.all()[:500]})
