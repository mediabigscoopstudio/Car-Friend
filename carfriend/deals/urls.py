from django.urls import path

from deals import views

urlpatterns = [
    path("<int:pk>/agreement/",                  views.deal_agreement,        name="deal_agreement"),
    path("<int:pk>/agreement/dealer/",           views.deal_agreement_dealer, name="deal_agreement_dealer"),
    path("<int:pk>/esign/<str:party>/start/",    views.esign_start,           name="esign_start"),
    path("<int:pk>/esign/<str:party>/callback/", views.esign_callback,        name="esign_callback"),
    path("<int:pk>/sold/",                       views.deal_sold,             name="deal_sold"),
]
