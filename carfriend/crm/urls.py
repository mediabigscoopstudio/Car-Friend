from django.urls import path
from crm import views
from crm import views_lead_manager as lm
from crm import views_retail as retail
from crm import views_dashboards as dash
from deals import views_procurement as proc
from auctions import views_ocb as ocb

urlpatterns = [
    # Teams dashboard
    path('',                                         views.teams_dashboard,   name='teams_dashboard'),

    # ── Role-scoped landing dashboards (one view + template per role) ──
    path('crm/retail/dashboard/',        dash.retail_dashboard,       name='dash_retail'),
    path('crm/sales/dashboard/',         dash.sales_dashboard,        name='dash_sales'),
    path('crm/lead-manager/dashboard/',  dash.lead_manager_dashboard, name='dash_lead_manager'),

    # Lead Manager (role-scoped)
    path('lead-manager/',                            lm.lm_dashboard,         name='lm_dashboard'),
    path('lead-manager/calendar/',                   lm.lm_calendar,          name='lm_calendar'),
    path('lead-manager/calendar/events/',            lm.lm_calendar_events,   name='lm_calendar_events'),
    path('lead-manager/inspection/<int:visit_id>/',  lm.lm_inspection_detail, name='lm_inspection_detail'),
    path('lead-manager/<int:lead_id>/qualify/',      lm.lm_qualify,           name='lm_qualify'),
    path('lead-manager/<int:lead_id>/assign/',       lm.lm_assign_inspection, name='lm_assign_inspection'),

    # Retail Associate (role-scoped: pipeline + OCB)
    path('retail/',                                  retail.retail_pipeline,  name='retail_pipeline'),
    path('retail/lead/<int:lead_id>/',               retail.retail_lead_detail, name='retail_lead_detail'),

    # Procurement Associate (role-scoped)
    path('procurement/',                             proc.proc_dashboard,     name='proc_dashboard'),
    path('procurement/completed/',                   proc.proc_completed,     name='proc_completed'),
    path('procurement/<int:deal_id>/',               proc.proc_handover,      name='proc_handover'),
    path('procurement/<int:deal_id>/complete/',      proc.proc_complete,      name='proc_complete'),

    # OCB task board — Retail (My OCBs) + Sales (open board) + shared detail
    path('ocb/',                                     ocb.ocb_board,           name='ocb_board'),
    path('ocb/create/',                              ocb.ocb_create,          name='ocb_create'),
    path('ocb/sales/',                               ocb.ocb_sales,           name='ocb_sales'),
    path('ocb/offer/<int:offer_id>/select/',         ocb.ocb_select,          name='ocb_select'),
    path('ocb/<int:listing_id>/',                    ocb.ocb_detail,          name='ocb_detail'),
    path('ocb/<int:listing_id>/offer/',              ocb.ocb_submit_offer,    name='ocb_submit_offer'),
    path('ocb/<int:listing_id>/message/',            ocb.ocb_message,         name='ocb_message'),

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
]
