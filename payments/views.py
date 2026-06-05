from django.shortcuts import render


def index(request):
    return render(
        request,
        "app_index.html",
        {
            "title": "Payments",
            "does": "handles manual payment confirmation via screenshot/scan upload and "
            "the payment audit trail.",
        },
    )

# Create your views here.
