import datetime
import io
import logging
import os
import subprocess
import tempfile
import uuid

from django.conf import settings
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

# Inspection media is standardised on light, web + Flutter-playable formats:
# photos → WebP, video → MP4 (H.264 + AAC), engine audio → M4A (AAC).
WEBP_QUALITY = 80
WEBP_MAX_EDGE = 1920       # cap longest edge to keep files light
VIDEO_CRF = 28             # H.264 quality/size balance (raise to 30-32 for smaller)
VIDEO_MAX_WIDTH = 1280     # cap width (~720p), keep aspect ratio, downscale only
VIDEO_TIMEOUT = 600        # up to 10 min — a 400 MB source transcode is slow


def convert_to_webp(media, raw_file):
    """Convert an uploaded inspection photo to WebP → media.webp_file (save=False).

    Resizes down so the longest edge is <= WEBP_MAX_EDGE. If a masked image
    already exists (license-plate pipeline), that processed image is the source
    of truth and gets converted instead of the raw upload.

    Returns True on success. On ANY failure it logs the full traceback loudly
    and returns False — the caller keeps the raw upload so nothing is lost and
    the request never crashes. The WebP file is written to storage here (before
    the DB record is committed by the caller).
    """
    try:
        from PIL import Image

        source = media.masked_file if media.masked_file else raw_file
        if hasattr(source, "seek"):
            source.seek(0)
        img = Image.open(source).convert("RGB")
        if max(img.size) > WEBP_MAX_EDGE:
            img.thumbnail((WEBP_MAX_EDGE, WEBP_MAX_EDGE), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=WEBP_QUALITY, method=4)
        slot = (media.slot or "img").replace(" ", "_").lower()
        media.webp_file.save(f"photo_{slot}.webp", ContentFile(buf.getvalue()), save=False)
        return True
    except Exception:
        logger.exception(
            "WebP conversion FAILED for inspection photo (report=%s slot=%s) — "
            "keeping the raw upload. Check Pillow/libwebp is installed.",
            getattr(getattr(media, "report", None), "id", "?"), getattr(media, "slot", ""),
        )
        return False


def _ffmpeg_to_temp(raw_file, args, out_suffix, label, pk, timeout=240):
    """Run ffmpeg on raw_file and return the output bytes, or None on failure.

    Large uploads (FILE_UPLOAD_MAX_MEMORY_SIZE is small) are spooled to a temp
    file on disk by Django; when so, we feed that path to ffmpeg directly
    instead of copying hundreds of MB again. None means the transcode did not
    run/failed — the caller keeps the raw upload (it never crashes the request).
    """
    own_input = False  # True when we created the temp input and must delete it
    in_path = getattr(raw_file, "temporary_file_path", None)
    if callable(in_path):
        in_path = raw_file.temporary_file_path()
    else:
        raw_file.seek(0)
        in_suffix = os.path.splitext(getattr(raw_file, "name", ""))[1] or ".bin"
        with tempfile.NamedTemporaryFile(suffix=in_suffix, delete=False) as tmp_in:
            for chunk in raw_file.chunks():
                tmp_in.write(chunk)
            in_path = tmp_in.name
        own_input = True

    out_path = in_path + "_cf" + out_suffix
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", in_path, *args, out_path],
            capture_output=True, timeout=timeout,
        )
        if result.returncode == 0 and os.path.exists(out_path):
            with open(out_path, "rb") as f:
                return f.read()
        logger.error(
            "ffmpeg %s transcode failed for media %s (rc=%s): %s",
            label, pk, result.returncode, result.stderr[-1200:].decode("utf-8", "replace"),
        )
        return None
    except FileNotFoundError:
        logger.error(
            "ffmpeg is NOT installed — cannot transcode inspection %s for media %s. "
            "Install ffmpeg on the VPS (e.g. `apt install ffmpeg`).", label, pk,
        )
        return None
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg %s transcode timed out (%ss) for media %s", label, timeout, pk)
        return None
    finally:
        if os.path.exists(out_path):
            os.unlink(out_path)
        if own_input and os.path.exists(in_path):
            os.unlink(in_path)


def is_web_ready_audio(upload):
    """True if the upload is already a web-playable audio format (mp3/m4a/aac)."""
    name = (getattr(upload, "name", "") or "").lower()
    ctype = (getattr(upload, "content_type", "") or "").lower()
    return name.endswith((".mp3", ".m4a", ".aac")) or ctype in (
        "audio/mpeg", "audio/mp3", "audio/mp4", "audio/aac", "audio/x-m4a",
    )


def convert_to_mp4(media, raw_file):
    """Compress ANY uploaded video to a light, streamable MP4 (H.264 + AAC,
    ~720p, faststart) → media.mp4_file (save=False).

    Runs even when the source is already MP4 — a 400 MB mp4 still needs
    compressing. Returns True on success; False if ffmpeg is unavailable or the
    transcode failed (caller keeps the raw upload, never crashes).
    """
    data = _ffmpeg_to_temp(
        raw_file,
        ["-vcodec", "libx264", "-crf", str(VIDEO_CRF), "-preset", "veryfast",
         "-vf", f"scale='min({VIDEO_MAX_WIDTH},iw)':-2",
         "-acodec", "aac", "-b:a", "128k",
         "-movflags", "+faststart"],
        ".mp4", "video", media.pk, timeout=VIDEO_TIMEOUT,
    )
    if data is None:
        return False
    media.mp4_file.save(f"video_{uuid.uuid4().hex}.mp4", ContentFile(data), save=False)
    return True


def convert_audio(media, raw_file):
    """Transcode uploaded engine audio to M4A (AAC) → media.file (save=False).

    Returns True on success. On failure the raw upload (often already an mp3)
    is left in place as a playable fallback; the failure is logged.
    """
    data = _ffmpeg_to_temp(
        raw_file,
        ["-vn", "-c:a", "aac", "-b:a", "128k"],
        ".m4a", "audio", media.pk,
    )
    if data is None:
        return False
    media.file.save(f"audio_{uuid.uuid4().hex}.m4a", ContentFile(data), save=False)
    return True


def mask_plate_and_watermark(media):
    """
    Detect the number plate, overlay the Car Friend logo, then stamp GPS + timestamp watermark.
    Saves to media.masked_file and sets plate_masked = True.
    """
    from PIL import Image, ImageDraw

    img = Image.open(media.file).convert("RGB")
    draw = ImageDraw.Draw(img)

    boxes = _detect_plate_boxes(img)
    logo_path = settings.CARFRIEND_LOGO_PATH
    if logo_path.exists():
        logo = Image.open(logo_path).convert("RGBA")
        for (x, y, w, h) in boxes:
            draw.rectangle([x, y, x + w, y + h], fill=(13, 15, 19))
            lg = logo.resize((w, h))
            img.paste(lg, (x, y), lg)
    else:
        for (x, y, w, h) in boxes:
            draw.rectangle([x, y, x + w, y + h], fill=(13, 15, 19))

    ts = (media.captured_at or datetime.datetime.now()).strftime("%d %b %Y · %H:%M")
    gps = f"{media.gps_lat:.5f}, {media.gps_lng:.5f}" if media.gps_lat else ""
    draw.text((12, img.height - 28), f"Car Friend · {ts}  {gps}", fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=78)
    media.masked_file.save(f"masked_{media.pk}.jpg", ContentFile(buf.getvalue()), save=False)
    media.plate_masked = True
    media.save(update_fields=["masked_file", "plate_masked"])
    return media


def _detect_plate_boxes(pil_img):
    """Return list of (x,y,w,h) using OpenCV Haar cascade. Falls back to empty list."""
    try:
        import cv2
        import numpy as np

        arr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_russian_plate_number.xml"
        )
        return [tuple(map(int, b)) for b in cascade.detectMultiScale(gray, 1.1, 4)]
    except Exception:
        return []


def publish_guard(report):
    """Block publishing if any car photo has an unmasked plate."""
    unmasked = report.media.filter(kind="photo", plate_masked=False).count()
    if unmasked:
        raise ValueError(
            f"{unmasked} car photo(s) still have unmasked plates — cannot publish."
        )
    return True


def generate_report_pdf(report):
    try:
        from weasyprint import HTML
    except ImportError:
        return None
    from django.template.loader import render_to_string
    from django.core.files.base import ContentFile
    from .schema import CHECKPOINT_SCHEMA, PHOTO_SLOTS
    html = render_to_string("inspection/report_pdf.html", {
        "r": report,
        "v": report.visit.vehicle,
        "schema": CHECKPOINT_SCHEMA,
        "photo_slots": PHOTO_SLOTS,
        "media": report.media.all(),
        "report_no": f"{report.visit.vehicle.id:08d}/{report.id}",
    })
    pdf_bytes = HTML(string=html, base_url=".").write_pdf()
    report.pdf.save(f"report_{report.id}.pdf", ContentFile(pdf_bytes), save=True)
    return report.pdf


def generate_pdf(report):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    v = report.visit.vehicle
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, 800, f"Car Friend Inspection · {v.title}")
    c.setFont("Helvetica", 11)
    c.drawString(
        40, 778,
        f"Score {report.score}/100 · Grade {report.condition_grade} · "
        f"Est. value ₹{report.est_market_value:,}",
    )
    y = 750
    for sec, items in report.checkpoints.items():
        c.drawString(40, y, f"{sec.title()} — {len(items)} checkpoints")
        y -= 16
        if y < 80:
            c.showPage()
            y = 800
    c.showPage()
    c.save()
    report.pdf.save(f"report_{report.pk}.pdf", ContentFile(buf.getvalue()), save=True)
    return report.pdf
