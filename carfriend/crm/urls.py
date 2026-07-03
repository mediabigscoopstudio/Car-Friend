from django.urls import path
from crm import views
from crm import views_lead_manager as lm
from crm import views_retail as retail
from crm import views_sales as sales
from crm import views_dashboards as dash
from crm import views_procurement as pcr
from crm import views_retail_head as rh
from crm import views_sales_head as sh
from deals import views_procurement as proc
from auctions import views_ocb as ocb

urlpatterns = [
    # Teams dashboard
    path('',                                         views.teams_dashboard,   name='teams_dashboard'),

    # ── Role-scoped landing dashboards (one view + template per role) ──
    path('crm/retail/dashboard/',        dash.retail_dashboard,       name='dash_retail'),
    path('crm/sales/dashboard/',         dash.sales_dashboard,        name='dash_sales'),
    path('crm/lead-manager/dashboard/',           views.lead_manager_dashboard, name='lead_manager_dashboard'),
    path('crm/lead-manager/inspection-calendar/', views.lead_manager_calendar,  name='lead_manager_calendar'),
    path('crm/api/inspection-visits/',            views.inspection_visits_json, name='inspection_visits_json'),
    path('crm/procurement/dashboard/',   pcr.procurement_dashboard,   name='dash_procurement'),
    path('crm/procurement/queue/',                     pcr.procurement_queue,     name='procurement_queue'),
    path('crm/procurement/handover/<int:deal_id>/',    pcr.procurement_handover,  name='procurement_handover'),
    path('crm/procurement/completed/',                 pcr.procurement_completed, name='procurement_completed'),
    path('crm/inspection/dashboard/',    dash.inspection_dashboard,   name='dash_inspection'),
    path('crm/inspection/visits/',       dash.inspection_visits,      name='dash_inspection_visits'),

    # Lead Manager (role-scoped)
    path('lead-manager/',                            lm.lm_dashboard,         name='lm_dashboard'),
    path('lead-manager/calendar/',                   lm.lm_calendar,          name='lm_calendar'),
    path('lead-manager/calendar/events/',            lm.lm_calendar_events,   name='lm_calendar_events'),
    path('lead-manager/inspection/<int:visit_id>/',  lm.lm_inspection_detail, name='lm_inspection_detail'),
    path('lead-manager/<int:lead_id>/qualify/',      lm.lm_qualify,           name='lm_qualify'),
    path('lead-manager/<int:lead_id>/assign/',       lm.lm_assign_inspection, name='lm_assign_inspection'),

    # Retail Associate (role-scoped: pipeline + OCB + tasks)
    path('crm/retail/pipeline/',                       retail.retail_pipeline,         name='retail_pipeline'),
    path('crm/retail/lead/<int:lead_id>/',             retail.retail_lead_detail,      name='retail_lead_detail'),
    path('crm/retail/lead/<int:lead_id>/create-auction/', retail.retail_create_auction, name='retail_create_auction'),
    path('crm/retail/ocb/',                            retail.retail_ocb_list,         name='retail_ocb_list'),
    path('crm/retail/ocb/create/',                     retail.retail_ocb_create,       name='retail_ocb_create'),
    path('crm/retail/ocb/<int:ocb_id>/',               retail.retail_ocb_detail,       name='retail_ocb_detail'),
    path('crm/retail/ocb/<int:ocb_id>/select-winner/', retail.retail_ocb_select_winner, name='retail_ocb_select_winner'),
    path('crm/retail/tasks/',                          retail.retail_task_list,        name='retail_task_list'),
    path('crm/retail/tasks/create/',                   retail.retail_task_create,      name='retail_task_create'),
    path('crm/retail/tasks/<int:task_id>/',            retail.retail_task_detail,      name='retail_task_detail'),
    path('crm/retail/tasks/<int:task_id>/status/',     retail.retail_task_status_update, name='retail_task_status_update'),

    # Retail Head (teams oversight: allocate + track the whole retail pool)
    path('crm/retail-head/',                rh.rh_approved_leads,  name='rh_approved_leads'),
    path('crm/retail-head/allocate/',       rh.rh_allocate,        name='rh_allocate'),
    path('crm/retail-head/associates/',     rh.rh_associates,      name='rh_associates'),
    path('crm/retail-head/sellers/',        rh.rh_sellers,         name='rh_sellers'),
    path('crm/retail-head/auctions/',       rh.rh_auctions,        name='rh_auctions'),
    path('crm/retail-head/lead-tracking/',  rh.rh_lead_tracking,   name='rh_lead_tracking'),
    path('crm/retail-head/reallocate/',     rh.rh_reallocate,      name='rh_reallocate'),
    path('crm/retail-head/lead/<int:lead_id>/',               rh.rh_lead_detail,   name='rh_lead_detail'),
    path('crm/retail-head/lead/<int:lead_id>/start-auction/', rh.rh_start_auction, name='rh_start_auction'),

    # Sales Associate (role-scoped: OCB assigned-only + restricted tasks)
    path('crm/sales/ocb/',                             sales.sales_ocb_list,           name='sales_ocb_list'),
    path('crm/sales/ocb/<int:ocb_id>/',                sales.sales_ocb_detail,         name='sales_ocb_detail'),
    path('crm/sales/tasks/',                           sales.sales_task_list,          name='sales_task_list'),
    path('crm/sales/tasks/<int:task_id>/',             sales.sales_task_detail,        name='sales_task_detail'),
    path('crm/sales/tasks/<int:task_id>/note/',        sales.sales_task_add_note,      name='sales_task_add_note'),

    # Sales Head (teams oversight: OCB inbox + dealer allocation + tracking)
    path('crm/sales-head/',                   sh.sh_ocb_inbox,         name='sh_ocb_inbox'),
    path('crm/sales-head/assign/',            sh.sh_ocb_assign,        name='sh_ocb_assign'),
    path('crm/sales-head/associates/',        sh.sh_associates,        name='sh_associates'),
    path('crm/sales-head/dealers/',           sh.sh_dealers,           name='sh_dealers'),
    path('crm/sales-head/dealer-allocation/', sh.sh_dealer_allocation, name='sh_dealer_allocation'),
    path('crm/sales-head/allocate-dealers/',  sh.sh_allocate_dealers,  name='sh_allocate_dealers'),
    path('crm/sales-head/ocb-tracking/',      sh.sh_ocb_tracking,      name='sh_ocb_tracking'),

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
    path('pipeline/<int:lead_id>/note/',             views.lead_add_note,     name='lead_add_note'),
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
