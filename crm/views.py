from django.shortcuts import render


def index(request):
    return render(
        request,
        "app_index.html",
        {
            "title": "CRM",
            "does": "runs the internal Retail and Sales pipelines, tasks, leads, deal "
            "assignment, and communication logs.",
        },
    )

# Create your views here.
