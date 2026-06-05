from django.shortcuts import render


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

# Create your views here.
