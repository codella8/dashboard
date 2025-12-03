# financial/urls.py
from django.urls import path
from . import views

app_name = "financial"

urlpatterns = [
    path("dashboard/", views.financial_dashboard, name="dashboard"),
    path("cashflow/", views.cashflow_overview, name="cashflow_overview"),
    path("timeseries/", views.cashbook_timeseries, name="cashbook_timeseries"),
    path("account/<uuid:account_id>/statement/", views.account_statement_view, name="account_statement"),
    path("outstanding/", views.outstanding_view, name="outstanding"),
]
