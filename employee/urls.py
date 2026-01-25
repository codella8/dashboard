from django.urls import path
from . import views

app_name = 'employee'

urlpatterns = [
    path('list/', views.employee_list, name='employee_list'),
    path('salary-payment/', views.process_salary_payment, name='salary_payment'),
    path('report/payroll/', views.payroll_report, name='payroll_report'),
    path('<uuid:employee_id>/', views.employee_detail, name='employee_detail'),
]
