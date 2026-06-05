import datetime
import io

from django.conf import settings
from django.core.files.base import ContentFile


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
