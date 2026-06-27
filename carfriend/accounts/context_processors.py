from accounts.models import Role

# Mirrors accounts.views.get_dashboard_url so the "My dashboard" header link
# always points at the logged-in user's real dashboard instead of being
# hard-coded to the seller/dealer one (which bounces staff/admin back to home).
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


def dashboard_link(request):
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {}
    return {"dashboard_url": _ROLE_DASHBOARD.get(user.role, "/")}
