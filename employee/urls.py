from django.urls import path
from . import views

app_name = 'employees'

urlpatterns = [
    path('', views.employee_dashboard, name='dashboard'),
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/<uuid:employee_id>/', views.employee_detail, name='employee_detail'),
    path('payroll/', views.payroll_report, name='payroll_report'),
    path('expenses/', views.expense_report, name='expense_report'),
    path('financial-status/', views.financial_status, name='financial_status'),
    path('department-analysis/', views.department_analysis, name='department_analysis'),
]