from django.shortcuts import render


def index(request):
    return render(
        request,
        "app_index.html",
        {
            "title": "Inspections",
            "does": "runs the 300+ checkpoint inspection form, photo capture with "
            "GPS/watermark, automatic license-plate masking, scoring, and PDF reports.",
        },
    )

# Create your views here.
