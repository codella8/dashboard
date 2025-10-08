from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_crm, name='home_crm.html')
]
