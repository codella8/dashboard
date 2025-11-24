from django.urls import path
from . import views

app_name = 'daily_sale'

urlpatterns = [
    
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/create/', views.create_transaction, name='create_transaction'),
    path('transactions/<uuid:transaction_id>/edit/', views.edit_transaction, name='edit_transaction'),
    path('transactions/<uuid:transaction_id>/delete/', views.delete_transaction, name='delete_transaction'),
    path('transactions/bulk-action/', views.bulk_action, name='bulk_action'),
    
    # گزارش‌ها و تحلیل‌ها
    path('dashboard/', views.dashboard, name='dashboard'),
    path('reports/financial/', views.financial_reports, name='financial_reports'),
    path('reports/analytics/', views.sales_analytics, name='sales_analytics'),
    path('reports/inventory/', views.inventory_reports, name='inventory_reports'),
    
    # API‌های هوشمند
    path('api/dashboard-stats/', views.api_dashboard_stats, name='api_dashboard_stats'),
    path('api/quick-summary/', views.api_quick_summary, name='api_quick_summary'),
    path('api/recent-activity/', views.api_recent_activity, name='api_recent_activity'),
    path('api/system-alerts/', views.api_system_alerts, name='api_system_alerts'),
    
    # مدیریت
    path('admin/control-panel/', views.admin_control_panel, name='admin_control_panel'),
    path('admin/bulk-operations/', views.admin_bulk_operations, name='admin_bulk_operations'),
]