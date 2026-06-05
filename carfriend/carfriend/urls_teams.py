from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from accounts import views as a
from crm import views as crm
from crm import views_sales as sales

urlpatterns = [
    path("", crm.pipeline, name="teams_home"),
    path("login_view", a.login_view, name="login_view"),
    path("logout_view", a.logout_view, name="logout_view"),
    # retail
    path("pipeline", crm.pipeline, name="pipeline"),
    path("seller/<int:id>", crm.seller_detail, name="seller_detail"),
    path("lead_move/<int:id>", crm.lead_move, name="lead_move"),
    path("add_offer/<int:id>", crm.add_offer, name="add_offer"),
    path("create_auction/<int:id>", crm.create_auction, name="create_auction"),
    path("add_comm", crm.add_comm, name="add_comm"),
    # tasks
    path("tasks", crm.tasks, name="tasks"),
    path("add_task", crm.add_task, name="add_task"),
    path("task_done/<int:id>", crm.task_done, name="task_done"),
    # sales
    path("dealers", sales.dealers, name="dealers"),
    path("dealer/<int:id>", sales.dealer_detail, name="dealer_detail"),
    path("deals", sales.deal_pipeline, name="deal_pipeline"),
    path("ocb", sales.ocb_assign, name="ocb"),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
