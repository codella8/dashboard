from django.urls import path
from . import views

app_name = "employee"

urlpatterns = [
    path('', views.home_employee, name='home_employee')
]
