from django.urls import path
from crm import views

urlpatterns = [
    # Teams dashboard
    path('',                                         views.teams_dashboard,   name='teams_dashboard'),

    # Lead pipeline
    path('pipeline/',                                views.pipeline,          name='pipeline'),
    path('pipeline/<int:lead_id>/',                  views.lead_detail,       name='lead_detail'),
    path('pipeline/<int:lead_id>/move/',             views.lead_move,         name='lead_move'),
    path('pipeline/<int:lead_id>/assign-inspector/', views.assign_inspector,  name='assign_inspector'),

    # Sellers
    path('sellers/',                                 views.sellers,           name='sellers'),

    # Dealer network
    path('dealers/',                                 views.dealers,           name='dealers'),
    path('dealers/<int:dealer_id>/',                 views.dealer_detail,     name='dealer_detail'),

    # Deals
    path('deals/',                                   views.deals,             name='deals'),
    path('deals/<int:vehicle_id>/',                  views.deal_detail,       name='deal_detail'),

    # Inspector
    path('inspector/',                               views.inspector_dashboard, name='inspector_dashboard'),
    path('inspector/<int:job_id>/',                  views.inspector_job,     name='inspector_job'),
    path('inspector/<int:job_id>/submit/',           views.submit_report,     name='submit_report'),
]
