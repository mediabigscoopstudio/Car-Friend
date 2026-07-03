from django.urls import path

from support import views

urlpatterns = [
    path("",                    views.support_home,  name="support_home"),
    path("faq/",                views.support_faq,   name="support_faq"),
    path("new/",                views.ticket_new,    name="ticket_new"),
    path("tickets/",            views.my_tickets,    name="my_tickets"),
    path("tickets/<int:pk>/",   views.ticket_detail, name="ticket_detail"),
]
