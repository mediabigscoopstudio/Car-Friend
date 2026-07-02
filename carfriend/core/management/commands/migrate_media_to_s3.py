import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Upload everything under MEDIA_ROOT to the S3 bucket, preserving relative paths."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="List what would upload; upload nothing.")

    def handle(self, *args, **opts):
        dry = opts["dry_run"]
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

        total = uploaded = skipped = failed = 0
        for root, _dirs, files in os.walk(media_root):
            for name in files:
                total += 1
                local_path = os.path.join(root, name)
                key = os.path.relpath(local_path, media_root).replace(os.sep, "/")
                local_size = os.path.getsize(local_path)

                # Idempotent: skip if the object already exists with the same size.
                exists_same = False
                try:
                    head = s3.head_object(Bucket=bucket, Key=key)
                    exists_same = head["ContentLength"] == local_size
                except ClientError as e:
                    code = e.response.get("Error", {}).get("Code", "")
                    if code not in ("404", "NoSuchKey", "NotFound"):
                        self.stderr.write(f"  head failed for {key}: {e}")
                if exists_same:
                    skipped += 1
                    continue

                if dry:
                    self.stdout.write(f"  WOULD UPLOAD  {key}  ({local_size} bytes)")
                    uploaded += 1
                    continue
                try:
                    s3.upload_file(local_path, bucket, key)
                    uploaded += 1
                    self.stdout.write(f"  uploaded  {key}")
                except Exception as e:
                    failed += 1
                    self.stderr.write(f"  FAILED  {key}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"\n{'DRY RUN — ' if dry else ''}Done. total={total} "
            f"{'would-upload' if dry else 'uploaded'}={uploaded} skipped={skipped} failed={failed}"))
