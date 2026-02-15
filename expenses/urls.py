# urls.py
from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    path('', views.expense_list, name='expense_list'),
    path('<int:pk>/', views.expense_detail, name='expense_detail'),
]