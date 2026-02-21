# daily_sale/urls.py
from django.urls import path
from . import views

app_name = "daily_sale"

urlpatterns = [
    path("cleared_transactions/", views.cleared_transactions, name="cleared_transactions"),
    path("create/", views.transaction_create, name="transaction_create"),
    path("transactions/", views.transaction_list, name="transaction_list"),
    path("old_transactions", views.transaction_list, name="old_transactions"),
    path("daily-summary/", views.daily_summary, name="daily_summary"),
    path("outstanding/", views.outstanding_view, name="outstanding"),
    path('customer/transaction/<uuid:transaction_id>/edit/', views.customer_transaction_edit, name='customer_transaction_edit'),
    path('customers/', views.customer_detail, name='customer_detail'),
    path('ajax/items/', views.ajax_search_items, name='ajax_search_items'),
    path('ajax/companies/', views.ajax_search_companies, name='ajax_search_companies'),
    path('ajax/customers/', views.ajax_search_customers, name='ajax_search_customers'),
    path('ajax/containers/', views.ajax_search_containers, name='ajax_search_containers'),
    path('ajax/item-autofill/', views.ajax_item_autofill, name='ajax_item_autofill'),
    path('transactions/<uuid:pk>/', views.invoice_view, name='invoice'),
    path('transactions/<uuid:pk>/', views.detail_view, name='detail'),
    path('transaction/<int:pk>/invoice/download/', views.download_invoice_pdf, name='download_invoice_pdf'),
    path('transaction/<uuid:pk>/delete/', views.transaction_delete, name='transaction_delete'),
    

]


