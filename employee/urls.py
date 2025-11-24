# employee/urls.py
from django.urls import path
from . import views

app_name = "employee"

urlpatterns = [
    path("", views.employee_list_view, name="list"),
    path("overview/", views.employees_financial_overview, name="overview"),
    path("<uuid:pk>/", views.employee_detail_view, name="detail"),
    path("<uuid:pk>/timeseries/", views.employee_timeseries_api, name="timeseries_api"),
]
