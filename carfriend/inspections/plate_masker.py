# inspections/plate_masker.py
# ---------------------------------------------------------------------------
# License-plate masking for inspection car photos.
#
# Covers the detected number plate with the Car Friend logo and overwrites the
# original file in place. Detection order:
#   1. Plate-specific YOLO model  — ONLY if settings.PLATE_YOLO_MODEL points at a
#      real plate model (the stock yolov8n.pt is COCO and has no 'plate' class,
#      so it is intentionally NOT used here).
#   2. OpenCV Haar cascade        — haarcascade_russian_plate_number (ships with
#      opencv-python-headless, already installed).
#   3. Contour heuristic          — scan the bottom 25% / top 15% of the frame
#      for rectangular contours with a plate-like aspect ratio (2.5–6).
#
# Never raises: returns True (masked), False (no plate found), or None (error,
# logged). All heavy imports are lazy so importing this module is always safe.
# ---------------------------------------------------------------------------
import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_LOGO = settings.BASE_DIR / "static" / "images" / "Logo" / "Logo.png"


def _yolo_boxes(cv_img):
    """Plate boxes from a plate-specific ultralytics model, if configured."""
    model_path = getattr(settings, "PLATE_YOLO_MODEL", None)
    if not model_path:
        return None
    try:
        from ultralytics import YOLO
        model = YOLO(model_path)
        res = model.predict(cv_img, verbose=False)
        boxes = []
        for r in res:
            for b in getattr(r, "boxes", []):
                x1, y1, x2, y2 = (int(v) for v in b.xyxy[0].tolist())
                boxes.append((x1, y1, x2 - x1, y2 - y1))
        return boxes or None
    except Exception:
        logger.exception("YOLO plate detection failed; falling back to OpenCV")
        return None


def _haar_boxes(cv_gray):
    import cv2
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_russian_plate_number.xml")
    return [tuple(map(int, b)) for b in cascade.detectMultiScale(cv_gray, 1.1, 4)]


def _contour_boxes(cv_img):
    """Heuristic: rectangular, plate-aspect contours in the bottom/top bands."""
    import cv2
    import numpy as np  # noqa: F401  (cv2 needs numpy present)
    h, w = cv_img.shape[:2]
    boxes = []
    for (y0, y1) in [(int(h * 0.75), h), (0, int(h * 0.15))]:
        region = cv_img[y0:y1]
        if region.size == 0:
            continue
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        edged = cv2.Canny(gray, 30, 200)
        cnts, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x, y, ww, hh = cv2.boundingRect(c)
            if hh < 12 or ww < w * 0.12:
                continue
            ar = ww / float(hh)
            if 2.5 <= ar <= 6.0:
                boxes.append((x, y0 + y, ww, hh))
    return boxes


def mask_license_plate(image_path, logo_path=None):
    """Detect the plate in `image_path`, cover it with the Car Friend logo, and
    overwrite the file. Returns True/False/None (masked / none found / error)."""
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw
    except Exception:
        logger.exception("plate masking dependencies (opencv/Pillow) unavailable")
        return None

    try:
        pil = Image.open(image_path).convert("RGB")
        cv_img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

        boxes = _yolo_boxes(cv_img)
        if not boxes:
            boxes = _haar_boxes(cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY))
        if not boxes:
            boxes = _contour_boxes(cv_img)
        if not boxes:
            return False                      # no plate — leave the image as-is

        logo = None
        lp = str(logo_path or DEFAULT_LOGO)
        try:
            if os.path.exists(lp):
                logo = Image.open(lp).convert("RGBA")
        except Exception:
            logger.exception("could not open mask logo %s", lp)

        draw = ImageDraw.Draw(pil)
        for (x, y, w, h) in boxes:
            if w <= 0 or h <= 0:
                continue
            draw.rectangle([x, y, x + w, y + h], fill=(13, 15, 19))
            if logo is not None:
                pil.paste(logo.resize((w, h)), (x, y), logo.resize((w, h)))

        ext = os.path.splitext(image_path)[1].lstrip(".").upper()
        if ext in ("JPG", "JPEG", ""):
            pil.save(image_path, "JPEG", quality=85)
        elif ext == "WEBP":
            pil.save(image_path, "WEBP", quality=85)
        elif ext == "PNG":
            pil.save(image_path, "PNG")
        else:
            pil.save(image_path)
        return True
    except Exception:
        logger.exception("plate masking failed for %s", image_path)
        return None
