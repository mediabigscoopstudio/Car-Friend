from django.shortcuts import render


def index(request):
    return render(
        request,
        "app_index.html",
        {
            "title": "Auctions",
            "does": "powers the 30-minute live auction engine - real-time bidding, "
            "countdown, re-activation, OCB, and the seller's post-auction decision.",
        },
    )

# Create your views here.
