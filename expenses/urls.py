from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    path('', views.expense_dashboard, name='expense_dashboard'),
    path('report/', views.expense_report, name='report'),
]