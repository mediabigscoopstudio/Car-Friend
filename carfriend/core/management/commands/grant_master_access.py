import os
from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    help = "Ensure a user has admin role and can access the master dashboard"

    def add_arguments(self, parser):
        parser.add_argument("username", nargs="?", default="Minaketan")
        parser.add_argument("--password", help="Reset password to this value")

    def handle(self, *args, **options):
        username = options["username"]
        new_password = options.get("password")

        try:
            user = User.objects.get(username__iexact=username)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'User "{username}" not found.'))
            self.stderr.write("Run: python manage.py createsuperuser")
            return

        changed = []

        if user.role != "admin":
            user.role = "admin"
            changed.append("role → admin")

        if not user.is_internal:
            user.is_internal = True
            changed.append("is_internal → True")

        if user.is_suspended:
            user.is_suspended = False
            changed.append("is_suspended → False")

        if not user.is_staff:
            user.is_staff = True
            changed.append("is_staff → True")

        if new_password:
            user.set_password(new_password)
            changed.append(f"password reset")

        user.save()

        parent_host = os.environ.get("PARENT_HOST", "localhost")
        master_url = f"http://master.{parent_host}/login_view"

        self.stdout.write(self.style.SUCCESS(f'\n✓ User: {user.username}'))
        if changed:
            for c in changed:
                self.stdout.write(f'  · {c}')
        else:
            self.stdout.write('  · already configured correctly')

        self.stdout.write(f'\nMaster login URL:')
        self.stdout.write(self.style.HTTP_INFO(f'  {master_url}'))
        self.stdout.write('')
