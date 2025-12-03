from django.urls import path
from . import views

app_name = 'daily_sale'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('create/', views.transaction_create, name='transaction_create'),
    path('edit/<uuid:pk>/', views.transaction_edit, name='transaction_edit'),
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('daily-summary/', views.daily_summary, name='daily_summary'),
    path('old_transactions/', views.old_transactions_view, name='old_transactions'),
    # AJAX endpoints
    path('ajax/containers/', views.ajax_search_containers, name='ajax_containers'),
    path('ajax/items/', views.ajax_search_items, name='ajax_items'),
    path('ajax/companies/', views.ajax_search_companies, name='ajax_companies'),
    path('ajax/customers/', views.ajax_search_customers, name='ajax_customers'),
]
