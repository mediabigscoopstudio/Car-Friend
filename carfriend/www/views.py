from django.shortcuts import render


def index(request):
    return render(request, "www/index.html")


def how_it_works(request):
    return render(request, "www/how_it_works.html")


def about(request):
    return render(request, "www/about.html")


def contact(request):
    return render(request, "www/contact.html")


def terms(request):
    return render(request, "www/policies/terms.html")


def privacy(request):
    return render(request, "www/policies/privacy.html")


def cookies(request):
    return render(request, "www/policies/cookies.html")


def auction_rules(request):
    return render(request, "www/policies/auction_rules.html")


def seller_agreement(request):
    return render(request, "www/policies/seller_agreement.html")


def refund_policy(request):
    return render(request, "www/policies/refund_policy.html")


def kyc_policy(request):
    return render(request, "www/policies/kyc_policy.html")


def inspection_policy(request):
    return render(request, "www/policies/inspection_policy.html")


def grievance(request):
    return render(request, "www/policies/grievance.html")
