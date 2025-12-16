from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_user, name='login'),
    path('signup/', views.signup_user, name='signup'),
    path('logout/', views.logout_user, name='logout'),
    
    # داشبورد - فقط برای ادمین‌ها
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # پنل ادمین Django
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    
    # صفحه کاربران عادی بعد از login
    path('user-home/', views.user_home, name='user_home'),
    
    # پروفایل
    path('update/', views.update_user, name='update_user'),
    path('update-password/', views.update_password, name='update_password'),
]