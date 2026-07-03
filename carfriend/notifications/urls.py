from django.urls import path

from notifications import views

urlpatterns = [
    path("",                views.notifications_inbox,   name="notifications_inbox"),
    path("read-all/",       views.notifications_read_all, name="notifications_read_all"),
    path("<int:pk>/open/",  views.notification_open,     name="notification_open"),
]
