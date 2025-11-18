from django.urls import path
from . import views
from .views import admin_panel

app_name = 'accounts' 

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('home/', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('logout/', views.logout_user, name='logout'),
    path('signup/', views.signup_user, name ='signup'),
    path('login/', views.login_user, name='login'),
    path('update_user/', views.update_user, name ='update_user'),
    path('update_info/', views.update_info, name ='update_info'),
    path('update_password/', views.update_password, name ='update_password'),
] 
 