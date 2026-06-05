from django.shortcuts import render


def index(request):
    return render(
        request,
        "app_index.html",
        {
            "title": "KYC",
            "does": "handles Aadhaar/PAN/GST verification, Aadhaar e-Sign, and the secure "
            "document vault.",
        },
    )

# Create your views here.
