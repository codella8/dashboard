from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_inventory, name='home_inventory')
]
