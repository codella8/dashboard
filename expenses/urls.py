from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_expenses, name='home_expenses')
]
