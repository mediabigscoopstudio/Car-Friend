from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

from accounts import views as account_views

urlpatterns = [
    # Auth for the teams host (login/logout redirects)
    path('auth/', include('accounts.urls')),
    # All CRM routes
    path('', include('crm.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
