"""Maintenance-mode middleware (BSS-2026-CF-SPEC v3.1, Part F).

When MAINTENANCE_MODE is on, the PUBLIC www surface (home, buy, sell, listings,
public auction room) serves a branded maintenance page with HTTP 503. Staff
surfaces (master / teams / inspection / api) and auth/login stay fully usable so
the team can keep working. Fully reversible: flip MAINTENANCE_MODE=False.
"""

from django.conf import settings
from django.shortcuts import render

# Never gate these, even on the public host: staff/login/admin/api + assets.
EXEMPT_PREFIXES = (
    "/auth/", "/accounts/", "/admin/", "/django-admin/",
    "/api/", "/static/", "/media/",
)
# Public hosts served by urls_public (django_hosts host names).
PUBLIC_HOST_NAMES = ("www", "default")
STAFF_SUBDOMAINS = ("teams", "master", "inspection", "api")


class MaintenanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if (getattr(settings, "MAINTENANCE_MODE", False)
                and self._is_public(request)
                and not self._is_exempt(request)):
            resp = render(request, "core/maintenance.html", status=503)
            resp["Retry-After"] = "3600"
            return resp
        return self.get_response(request)

    @staticmethod
    def _is_public(request):
        # django_hosts sets request.host (a Host with .name) before this runs.
        name = getattr(getattr(request, "host", None), "name", None)
        if name:
            return name in PUBLIC_HOST_NAMES
        # Fallback if host routing isn't resolved: treat any non-staff subdomain
        # as public.
        sub = request.get_host().split(":")[0].split(".")[0].lower()
        return sub not in STAFF_SUBDOMAINS

    @staticmethod
    def _is_exempt(request):
        path = request.path
        return any(path.startswith(p) for p in EXEMPT_PREFIXES)
