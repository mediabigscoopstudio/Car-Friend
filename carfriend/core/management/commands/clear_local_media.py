import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = ("Delete local files under MEDIA_ROOT ONLY after verifying each exists in "
            "S3 with a matching size. Requires --confirm to actually delete. "
            "Run this yourself AFTER verifying migrate_media_to_s3 — it is never "
            "called automatically.")

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="Show what would be deleted; delete nothing.")
        parser.add_argument("--confirm", action="store_true",
                            help="Actually delete verified files (required to delete).")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
        confirm = opts["confirm"]
        if not dry and not confirm:
            raise CommandError("Refusing to delete without --confirm (use --dry-run to preview).")

        bucket = getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
        if not bucket:
            raise CommandError("AWS_STORAGE_BUCKET_NAME is not set — check your .env.")
        media_root = str(settings.MEDIA_ROOT)
        if not os.path.isdir(media_root):
            raise CommandError(f"MEDIA_ROOT does not exist: {media_root}")

        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError:
            raise CommandError("boto3 is not installed. Run: pip install boto3 django-storages")

        s3 = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_S3_REGION_NAME", "") or None,
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", "") or None,
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", "") or None,
        )
        preview = dry or not confirm     # anything but a real --confirm run is preview

        deleted = skipped = failed = 0
        freed = 0
        for root, _dirs, files in os.walk(media_root):
            for name in files:
                local_path = os.path.join(root, name)
                key = os.path.relpath(local_path, media_root).replace(os.sep, "/")
                local_size = os.path.getsize(local_path)

                verified = False
                try:
                    head = s3.head_object(Bucket=bucket, Key=key)
                    verified = head["ContentLength"] == local_size
                except ClientError:
                    verified = False
                if not verified:
                    skipped += 1
                    self.stdout.write(f"  KEEP (not confirmed in S3)  {key}")
                    continue

                if preview:
                    self.stdout.write(f"  WOULD DELETE  {key}  ({local_size} bytes)")
                    deleted += 1
                    freed += local_size
                    continue
                try:
                    os.remove(local_path)
                    deleted += 1
                    freed += local_size
                    self.stdout.write(f"  deleted  {key}")
                except Exception as e:
                    failed += 1
                    self.stderr.write(f"  FAILED to delete {key}: {e}")

        mb = freed / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(
            f"\n{'DRY RUN — ' if preview else ''}Done. "
            f"{'would-delete' if preview else 'deleted'}={deleted} "
            f"kept/not-in-S3={skipped} failed={failed} "
            f"space_{'would-free' if preview else 'freed'}={mb:.1f} MB"))
