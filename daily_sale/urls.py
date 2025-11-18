from django.urls import path
from . import views

app_name = 'daily_sale'

urlpatterns = [
    path('', views.dashboard_overview, name='dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),

    # صفحات گزارش و آنالیز
    path('sales-summary/', views.sales_summary_view, name='sales_summary'),
    path('sales-by-item/', views.sales_by_item_view, name='sales_by_item'),
    path('outstanding-customers/', views.outstanding_customers_view, name='outstanding_customers'),
    path('sales-purchases-range/', views.sales_and_purchases_range_view, name='sales_purchases_range'),
    path('financial-analytics/', views.financial_analytics_view, name='financial_analytics'),
    path('customer-analysis/', views.customer_analysis_view, name='customer_analysis'),
    path('container-sales/', views.container_sales_view, name='container_sales'),

    # مدیریت تراکنش‌ها (CRUD)
    path('transaction-list/', views.transaction_list_view, name='transaction_list'),
    path('transaction/create/', views.transaction_create_view, name='transaction_create'),
    path('transaction/<uuid:pk>/edit/', views.transaction_edit_view, name='transaction_edit'),
    path('transaction/<uuid:pk>/delete/', views.transaction_delete_view, name='transaction_delete'),

    # API endpoints (JSON) برای استفاده در داشبورد frontend (Chart.js / Ajax)
    path('api/real-time-stats/', views.real_time_stats_api, name='api_real_time_stats'),
    path('api/sales-timeseries/', views.sales_timeseries_api, name='api_sales_timeseries'),
    path('api/sales-by-item/', views.sales_by_item_api, name='api_sales_by_item'),
]
