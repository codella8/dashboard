from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_reports, name='home_reports')
]
