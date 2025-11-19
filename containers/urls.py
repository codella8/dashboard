from django.urls import path
from . import views
from .views import InventoryCreateView

app_name = "containers"

urlpatterns = [
    path("", views.ContainerListView.as_view(), name="list"),
    path("container/<uuid:container_id>/financial/", views.container_financial_report_view, name="container_financial_report"),
    path("transactions/report/", views.total_container_transactions_report_view, name="total_container_transactions_report"),
    path("sarafs/", views.SarafListView.as_view(), name="saraf_list"),
    path("saraf/<uuid:saraf_id>/", views.SarafDetailView.as_view(), name="saraf_detail"),
    path("sarafs/balance-report/", views.saraf_balance_report, name="saraf_balance_report"),
    path("admin/overview/", views.ContainersAdminOverview.as_view(), name="admin_overview"),
     path("inventory/add/", InventoryCreateView.as_view(), name="inventory_add"),
]
