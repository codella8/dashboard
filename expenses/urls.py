from django.urls import path
from . import views
app_name = "expenses"

urlpatterns = [
    path('', views.home_expenses, name='home_expenses')
]
