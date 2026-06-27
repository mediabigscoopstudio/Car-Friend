from accounts.models import Role

try:
    from django_hosts.resolvers import reverse as host_reverse
except ImportError:          # django_hosts always present in prod; guard for safety
    host_reverse = None

# Mirrors accounts.views.get_dashboard_url so the "My dashboard" header link
# always points at the logged-in user's real dashboard instead of being
# hard-coded to the seller/dealer one (which bounced staff/admin back to home).
_ROLE_DASHBOARD = {
    Role.SELLER:       "/auth/seller/dashboard/",
    Role.DEALER:       "/auth/dealer/dashboard/",
    Role.LEAD_MANAGER: "/crm/lead-manager/dashboard/",
    Role.RETAIL_HEAD:  "/crm/retail-head/",
    Role.SALES_HEAD:   "/crm/sales-head/",
    Role.RETAIL:       "/crm/retail/dashboard/",
    Role.SALES:        "/crm/sales/dashboard/",
    Role.INSPECTOR:    "/crm/inspection/dashboard/",
    Role.PROCUREMENT:  "/crm/procurement/dashboard/",
}


def _master_dashboard_url():
    """Admins live on the master subdomain, not the www site."""
    if host_reverse:
        try:
            return host_reverse("master_dashboard", host="master")
        except Exception:
            pass
    return "/"


def dashboard_link(request):
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {}
    url = _ROLE_DASHBOARD.get(user.role)
    if url is None:          # admin / internal staff
        url = _master_dashboard_url()
    return {"dashboard_url": url}
