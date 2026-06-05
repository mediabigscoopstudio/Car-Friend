from django.shortcuts import render


def index(request):
    return render(
        request,
        "app_index.html",
        {
            "title": "Notifications",
            "does": "sends push (FCM), WhatsApp, and SMS alerts across the platform.",
        },
    )

# Create your views here.
