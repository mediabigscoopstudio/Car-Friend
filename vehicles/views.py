from django.shortcuts import render


def index(request):
    return render(
        request,
        "app_index.html",
        {
            "title": "Vehicles",
            "does": "manages car listings - ownership, expected price, and "
            "RC/insurance/service-history documents.",
        },
    )

# Create your views here.
