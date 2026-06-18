"""Compress pending inspection videos to light, streamable MP4s — OUT of the
upload request.

Inspection videos are uploaded raw (needs_transcode=True, transcoded=False) and
served as-is immediately. This command finds those pending videos and replaces
each with a light H.264/AAC ~720p faststart MP4, deleting the heavy original.

Run manually:
    ../venv/bin/python manage.py transcode_pending_videos

Cron it (every 5 minutes) so uploads get compressed automatically — e.g.
`crontab -e` for the deploy user:
    */5 * * * * cd /var/www/carfriend/carfriend && \
      ../venv/bin/python manage.py transcode_pending_videos \
      >> /var/log/carfriend/transcode.log 2>&1

Safe to overlap-guard if needed (e.g. `flock`), but a single inspector's
backlog is tiny. Failures (ffmpeg missing/errors) leave the raw file in place
and needs_transcode=True so the next run retries; one bad file never stops the
batch.
"""
import os
import subprocess
import uuid

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from inspections.models import InspectionMedia
from inspections.services import VIDEO_CRF, VIDEO_MAX_WIDTH, VIDEO_TIMEOUT


def _human(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}"
        n /= 1024


def _safe_unlink(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


class Command(BaseCommand):
    help = "Transcode pending inspection videos to light streamable MP4 (run via cron)."

    def handle(self, *args, **options):
        qs = InspectionMedia.objects.filter(
            kind=InspectionMedia.Kind.VIDEO, needs_transcode=True, transcoded=False
        )
        total = qs.count()
        if not total:
            self.stdout.write("No pending videos.")
            return

        self.stdout.write(f"Found {total} pending video(s).")
        done = failed = 0
        saved_total = 0

        for media in qs.iterator():
            if not media.file:
                # No file to work on — clear the flag so it isn't retried forever.
                media.needs_transcode = False
                media.save(update_fields=["needs_transcode"])
                continue

            try:
                in_path = media.file.path
            except (NotImplementedError, ValueError):
                self.stderr.write(f"  media {media.id}: no local file path (remote storage?); skipped")
                failed += 1
                continue
            if not os.path.exists(in_path):
                self.stderr.write(f"  media {media.id}: raw file missing on disk; skipped")
                failed += 1
                continue

            before = os.path.getsize(in_path)
            out_path = f"{in_path}.cf_{uuid.uuid4().hex}.mp4"
            cmd = [
                "ffmpeg", "-y", "-i", in_path,
                "-vcodec", "libx264", "-crf", str(VIDEO_CRF), "-preset", "veryfast",
                "-vf", f"scale='min({VIDEO_MAX_WIDTH},iw)':-2",
                "-acodec", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                out_path,
            ]

            try:
                result = subprocess.run(cmd, capture_output=True, timeout=VIDEO_TIMEOUT)
            except FileNotFoundError:
                self.stderr.write(self.style.ERROR(
                    "ffmpeg is NOT installed — install it (e.g. `apt install ffmpeg`). "
                    "Leaving videos pending for the next run."
                ))
                break  # ffmpeg missing for all; stop, flags untouched → retried later
            except subprocess.TimeoutExpired:
                self.stderr.write(f"  media {media.id}: ffmpeg timed out ({VIDEO_TIMEOUT}s); left pending")
                _safe_unlink(out_path)
                failed += 1
                continue
            except Exception as e:  # never crash the whole batch on one file
                self.stderr.write(f"  media {media.id}: ffmpeg error {e!r}; left pending")
                _safe_unlink(out_path)
                failed += 1
                continue

            if result.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
                tail = result.stderr[-800:].decode("utf-8", "replace") if result.stderr else ""
                self.stderr.write(f"  media {media.id}: transcode failed (rc={result.returncode}); left pending")
                if tail:
                    self.stderr.write("    " + tail.replace("\n", "\n    "))
                _safe_unlink(out_path)
                failed += 1
                continue

            after = os.path.getsize(out_path)
            old_path = in_path
            try:
                with open(out_path, "rb") as fh:
                    media.file.save(f"{uuid.uuid4().hex}.mp4", ContentFile(fh.read()), save=False)
                media.transcoded = True
                media.needs_transcode = False
                media.save(update_fields=["file", "transcoded", "needs_transcode"])
            finally:
                _safe_unlink(out_path)

            # Delete the heavy raw original now that the light file is stored.
            if old_path and old_path != media.file.path:
                _safe_unlink(old_path)

            saved_total += max(0, before - after)
            done += 1
            pct = (after / before * 100) if before else 0
            self.stdout.write(
                f"  media {media.id}: {_human(before)} -> {_human(after)} ({pct:.0f}% of original)"
            )

        self.stdout.write(self.style.SUCCESS(
            f"Done. transcoded={done} failed={failed} space_saved={_human(saved_total)}"
        ))
