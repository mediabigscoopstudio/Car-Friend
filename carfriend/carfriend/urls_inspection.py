from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from inspections import views_app as v

urlpatterns = [
    path("", v.insp_dashboard, name="insp_dashboard"),
    path("login_view", v.insp_login, name="insp_login"),
    path("visits", v.insp_visits, name="insp_visits"),
    path("visit/<int:id>", v.insp_visit, name="insp_visit"),
    path("start/<int:id>", v.insp_start, name="insp_start"),
    path("inspection/<int:id>/<str:section>", v.insp_form, name="insp_form"),
    path("save/<int:id>", v.insp_save, name="insp_save"),
    path("upload/<int:id>", v.insp_upload_media, name="insp_upload_media"),
    path("report/<int:id>", v.insp_report, name="insp_report"),
    path("submit/<int:id>", v.insp_submit, name="insp_submit"),
    path("alerts", v.insp_alerts, name="insp_alerts"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
