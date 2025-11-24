from django.urls import path
from . import views

app_name = "reports"

urlpatterns = [
    path('home_reports', views.home_reports, name='home_reports')
]
