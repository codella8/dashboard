# daily_sale/urls.py
from django.urls import path
from . import views

app_name = "daily_sale"

urlpatterns = [
    path("cleared_transactions/", views.cleared_transactions, name="cleared_transactions"),
    path("create/", views.transaction_create, name="transaction_create"),
    path("edit/<uuid:pk>/", views.transaction_edit, name="transaction_edit"),
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("transactions/<uuid:pk>/", views.transaction_detail, name="transaction_detail"),
    path("daily-summary/", views.daily_summary, name="daily_summary"),
    path("outstanding/", views.outstanding_view, name="outstanding"),
    path('generate-report/', views.generate_daily_report, name='generate_daily_report'),
    # اضافه کنید در urlpatterns
    path('customers/', views.customer_detail, name='customer_detail'),

    path("ajax/containers/", views.ajax_search_containers, name="ajax_containers"),
    path("ajax/items/", views.ajax_search_items, name="ajax_items"),
    path("ajax/companies/", views.ajax_search_companies, name="ajax_companies"),
    path("ajax/customers/", views.ajax_search_customers, name="ajax_customers"),
]
