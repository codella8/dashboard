from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from daily_sale.models import DailySaleTransaction
from expenses.models import ExpenseItem
from containers.models import Container, Inventory_List
from .forms import SignUpForm, UserUpdateForm, UpdatePasswordForm, UpdateUserInfo
from .models import UserProfile
from django.contrib.auth.models import User
from django.utils.translation import gettext as _
from django.utils.translation import get_language
from functools import wraps

# Decorator سفارشی برای ادمین‌ها
def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, _("Please login first"))
            return redirect('accounts:login')
        if not request.user.is_staff:
            messages.error(request, _("Admin access required"))
            return redirect('accounts:home')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

# صفحه اصلی - برای همه
def home(request):    
    context = {
        'welcome_message': _("Hello Welcome!")
    }
    return render(request, 'home.html', context)

# صفحه login اصلاح شده
# accounts/views.py
def login_user(request):
    """Login view that handles user login with appropriate messages"""
    if request.user.is_authenticated:
        messages.info(request, _("You are already logged in!"))
        
        # اگر کاربر ادمین است به داشبورد، اگر کاربر عادی است به صفحه مشتری
        if request.user.is_staff:
            return redirect("accounts:dashboard")
        else:
            # کاربر عادی را به صفحه مشتری هدایت می‌کنیم
            return redirect("daily_sale:customer_detail")

    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        
        if not username or not password:
            messages.error(request, _("Please enter both username and password"))
        else:
            user = authenticate(request, username=username, password=password)

            if user:
                login(request, user)
                messages.success(request, _("Login successful!"))
                
                # بررسی next page
                next_page = request.GET.get('next')
                
                # اگر کاربر ادمین است
                if user.is_staff:
                    if next_page and '/admin/' in next_page:
                        return redirect(next_page)
                    return redirect('accounts:dashboard')
                # اگر کاربر عادی است
                else:
                    if next_page and ('/admin/' in next_page or '/dashboard/' in next_page):
                        messages.warning(request, _("Access denied. Redirecting to your profile."))
                        return redirect('dailysale:customer_self_view')
                    return redirect('dailysale:customer_self_view')
            else:
                messages.error(request, _("Incorrect username or password!"))

    return render(request, 'login.html')
# صفحه signup
def signup_user(request):
    """User registration view that handles form submission for user signup"""
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, _("Registration successful! You can now login."))
            return redirect('accounts:login')
        else:
            messages.error(request, _("Please correct the form errors"))
    else:
        form = SignUpForm()
    
    return render(request, 'signup.html', {'form': form})

# داشبورد - فقط برای ادمین‌ها
@login_required
@admin_required
def dashboard(request):
    """Admin Dashboard with quick stats and app navigation"""
    
    # Quick statistics - با داده‌های واقعی
    try:
        total_sales = DailySaleTransaction.objects.count()
    except:
        total_sales = 0
    
    try:
        total_expenses = ExpenseItem.objects.count()
    except:
        total_expenses = 0
    
    try:
        total_containers = Container.objects.count()
    except:
        total_containers = 0
    
    try:
        total_users = User.objects.count()
    except:
        total_users = 0
    
    quick_stats = {
        'total_sales': total_sales,
        'total_expenses': total_expenses,
        'total_containers': total_containers,
        'total_users': total_users,
    }
    
    # App navigation setup - با URLهای Django
    apps = [
        {
            'name': 'Daily Sales', 
            'url': 'daily_sale:transaction_list',  # با نام URL
            'icon': 'fas fa-shopping-cart', 
            'description': 'Daily transactions and sales management'
        },
        {
            'name': 'Containers', 
            'url': 'containers:list',  # با نام URL
            'icon': 'fas fa-shipping-fast', 
            'description': 'Container and shipping management'
        },
        {
            'name': 'Expenses', 
            'url': 'expenses:report/',  # با نام URL
            'icon': 'fas fa-money-bill-wave', 
            'description': 'Expense tracking and management'
        },
        {
            'name': 'Employees', 
            'url': 'employee:employees/',  # با نام URL
            'icon': 'fas fa-users',  
            'description': 'Employee and staff management'
        },
        {
            'name': 'Finance', 
            'url': '#',  # اگر وجود ندارد
            'icon': 'fas fa-chart-line', 
            'description': 'Financial reports and analysis'
        },
        {
            'name': 'Reports', 
            'url': '#',  # اگر وجود ندارد
            'icon': 'fas fa-file-alt', 
            'description': 'Comprehensive reporting system'
        },
    ]

    context = {
        'quick_stats': quick_stats,
        'apps': apps
    }
    return render(request, 'dashboard.html', context)

# پنل ادمین Django
@login_required
@admin_required
def admin_panel(request):
    """Redirect to Django admin panel"""
    return redirect('admin:index')

# logout
def logout_user(request):
    logout(request)
    messages.success(request, _("You Have Been Logged Out..."))
    return redirect('accounts:home')

# update user info
@login_required
def update_user(request):
    current_user = request.user  # استفاده از request.user که همیشه لاگین شده است
    user_form = UserUpdateForm(request.POST or None, instance=current_user)
    
    if request.method == "POST":
        if user_form.is_valid(): 
            user_form.save()
            # login(request, current_user)  # این خط را حذف کنید، چون کاربر قبلا لاگین است
            messages.success(request, _('Profile updated successfully!'))
            return redirect('accounts:home')
    
    return render(request, 'update_user.html', {'user_form': user_form})

# update password
@login_required
def update_password(request):
    current_user = request.user
    
    if request.method == 'POST':
        form = UpdatePasswordForm(current_user, request.POST)
        if form.is_valid():
            form.save()
            login(request, current_user)
            messages.success(request, _('Password changed successfully!'))
            return redirect('accounts:home')
        else:
            for error in list(form.errors.values()):
                messages.error(request, error)
    else:
        form = UpdatePasswordForm(current_user)

    return render(request, 'update_password.html', {'form': form})



# صفحه برای کاربران عادی - اگر به داشبورد دسترسی پیدا کردند
@login_required
def user_home(request):
    """Home page for regular users after login"""
    context = {
        'user': request.user,
        'is_admin': request.user.is_staff
    }
    return render(request, 'home.html', context)