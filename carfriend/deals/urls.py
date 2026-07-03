from django.urls import path

from deals import views

urlpatterns = [
    path("<int:pk>/agreement/", views.deal_agreement, name="deal_agreement"),
    path("<int:pk>/sold/",      views.deal_sold,      name="deal_sold"),
]
