from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response

from .models import InspectionReport, InspectionMedia, DentMarker
from .services import mask_plate_and_watermark


@api_view(["POST"])
def checkpoint_autosave(request, report_id):
    """Body: {section, key, val, sev}. Offline-first client batches these on reconnect."""
    r = InspectionReport.objects.get(pk=report_id)
    sec = r.checkpoints.setdefault(request.data["section"], {})
    sec[request.data["key"]] = {
        "val": request.data.get("val"),
        "sev": int(request.data.get("sev", 0)),
    }
    r.is_synced = True
    r.save(update_fields=["checkpoints", "is_synced"])
    return Response({"ok": True, "done": sum(len(s) for s in r.checkpoints.values())})


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def media_upload(request, report_id):
    """Upload a car photo — immediately masks the plate + watermark."""
    r = InspectionReport.objects.get(pk=report_id)
    m = InspectionMedia.objects.create(
        report=r,
        kind=request.data.get("kind", "photo"),
        section=request.data.get("section", ""),
        file=request.FILES["file"],
        gps_lat=request.data.get("gps_lat") or None,
        gps_lng=request.data.get("gps_lng") or None,
    )
    if m.kind == "photo":
        mask_plate_and_watermark(m)
    url = (m.masked_file.url if m.masked_file else m.file.url)
    return Response({"id": m.id, "plate_masked": m.plate_masked, "url": url})


@api_view(["POST"])
def dent_add(request, report_id):
    d = DentMarker.objects.create(
        report_id=report_id,
        x=float(request.data["x"]),
        y=float(request.data["y"]),
        label=request.data.get("label", ""),
        severity=int(request.data.get("severity", 1)),
    )
    return Response({"id": d.id})
