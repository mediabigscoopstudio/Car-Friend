from django.conf import settings
from django.urls import path, re_path
from django.views.static import serve

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
    path("media/<int:id>/delete", v.insp_delete_media, name="insp_delete_media"),
    path("checkpoint/<int:id>/photo", v.insp_checkpoint_photo, name="insp_checkpoint_photo"),
    path("checkpoint-photo/<int:photo_id>/delete", v.insp_checkpoint_photo_delete, name="insp_checkpoint_photo_delete"),
    path("report/<int:id>", v.insp_report, name="insp_report"),
    path("submit/<int:id>", v.insp_submit, name="insp_submit"),
    path("alerts", v.insp_alerts, name="insp_alerts"),
    # Serve uploaded media on the inspection host in EVERY environment.
    # The old `static(MEDIA_URL, ...)` helper is a no-op when DEBUG is False,
    # which left /media/ 404ing in production (photos broken, video/audio
    # unretrievable). This explicit route always resolves /media/<path>.
    # Listed last so it can't shadow `media/<id>/delete` above.
    # (Nginx may override this `location /media/` for performance if configured.)
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
