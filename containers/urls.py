from django.urls import path
from . import views 
app_name = 'containers' 

urlpatterns = [
    path('sarafs/', views.saraf_list, name='saraf_list'),
    path('saraf/<uuid:saraf_id>/transactions/', views.saraf_transactions_report, name='saraf_transactions_report'),
    path('saraf/balance-report/', views.saraf_balance_report, name='saraf_balance_report'),
    path('container/<uuid:container_id>/financial-report/', views.container_financial_report, name='container_financial_report'),
    path('container/total-transactions-report/', views.total_container_transactions_report, name='total_container_transactions_report'),
]

