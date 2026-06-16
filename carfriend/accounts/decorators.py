from functools import wraps
from django.shortcuts import redirect


def role_required(*roles, login_url="/login_view"):
    def deco(view):
        @wraps(view)
        def wrapper(request, *a, **k):
            u = request.user
            if not u.is_authenticated or u.is_suspended:
                return redirect(login_url)
            if u.role == "admin" or u.role in roles:
                return view(request, *a, **k)
            return redirect(login_url)
        return wrapper
    return deco


admin_required        = lambda v: role_required("admin")(v)
retail_required       = lambda v: role_required("retail")(v)
sales_required        = lambda v: role_required("sales")(v)
inspector_required    = lambda v: role_required("inspector")(v)
lead_manager_required = lambda v: role_required("lead_manager")(v)
procurement_required  = lambda v: role_required("procurement")(v)
