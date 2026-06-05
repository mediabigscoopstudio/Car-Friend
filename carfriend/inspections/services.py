import datetime
import io
import os
import subprocess
import tempfile

from django.conf import settings
from django.core.files.base import ContentFile


def convert_to_webp(media, raw_file):
    """Convert uploaded image to WebP and save to media.webp_file (save=False)."""
    from PIL import Image
    raw_file.seek(0)
    img = Image.open(raw_file).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=85, method=4)
    name = f"photo_{media.pk}_{(media.slot or 'img').replace(' ', '_').lower()}.webp"
    media.webp_file.save(name, ContentFile(buf.getvalue()), save=False)


def convert_to_mp4(media, raw_file):
    """Convert uploaded video to MP4 H.264+AAC via ffmpeg, save to media.mp4_file (save=False)."""
    raw_file.seek(0)
    suffix = os.path.splitext(getattr(raw_file, "name", ".mp4"))[1] or ".mp4"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_in:
        for chunk in raw_file.chunks():
            tmp_in.write(chunk)
        tmp_in_path = tmp_in.name

    tmp_out_path = tmp_in_path + "_cf.mp4"
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_in_path,
             "-c:v", "libx264", "-preset", "fast", "-crf", "23",
             "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart",
             tmp_out_path],
            capture_output=True, timeout=180,
        )
        if result.returncode == 0:
            with open(tmp_out_path, "rb") as f:
                media.mp4_file.save(f"video_{media.pk}.mp4", ContentFile(f.read()), save=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # ffmpeg not available — skip conversion
    finally:
        os.unlink(tmp_in_path)
        if os.path.exists(tmp_out_path):
            os.unlink(tmp_out_path)


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
