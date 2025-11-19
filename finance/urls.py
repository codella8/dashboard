from django.urls import path
from . import views

app_name = "finanace"

urlpatterns = [
    path('', views.home_finance, name='home_finance')
]
