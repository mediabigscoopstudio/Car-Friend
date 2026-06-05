from django.shortcuts import render


def index(request):
    return render(
        request,
        "app_index.html",
        {
            "title": "Accounts",
            "does": "manages user accounts, the six roles, role-based permissions, and "
            "login with automatic Seller/Dealer role detection.",
        },
    )

# Create your views here.
