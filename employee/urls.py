from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_employee, name='home_employee')
]
