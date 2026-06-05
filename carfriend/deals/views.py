from django.shortcuts import render


def index(request):
    return render(
        request,
        "app_index.html",
        {
            "title": "Deals",
            "does": "handles deal closure, agreement generation, Aadhaar e-Sign, and "
            "document linking.",
        },
    )

# Create your views here.
