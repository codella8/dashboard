from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from daily_sale.models import DailySaleTransaction
from expenses.models import ExpenseItem
from containers.models import Container, Inventory_List
from . forms import SignUpForm, UserUpdateForm, UpdatePasswordForm, UpdateUserInfo
from .models import UserProfile
from django.contrib.auth.models import User
from django.utils.translation import gettext as _
from django.contrib.auth.decorators import user_passes_test
from django.utils.translation import get_language
from functools import wraps

def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('accounts:login')
        if not request.user.is_staff:
            messages.error(request, _("Admin access required"))
            return redirect('accounts:home')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

@user_passes_test(admin_required) #فقط به ادمین‌ها اجازه ورود می‌دهد
def admin_panel(request):
    return redirect('admin:index')

def home(request):    
    context = {
        'welcome_message': _("Hello Welcome!")
    }
    return render(request, 'home.html', context)

def about(request):
    return render(request, 'about.html')


def login_user(request):
    """Login view that handles user login with appropriate messages"""
    if request.user.is_authenticated:
        messages.info(request, _("You are already logged in!"))
        return redirect("accounts:dashboard")  # Redirect to dashboard after login

    if request.method == "POST":
        username = request.POST.get('username').strip()
        password = request.POST.get('password').strip()
        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            next_page = request.GET.get('next', 'accounts:dashboard')
            if '/admin/' in next_page and not user.is_staff:
                messages.error(request, _("You don't have permission to access the admin panel"))
                return redirect('accounts:dashboard')

            return redirect(next_page)
        else:
            messages.error(request, _("Incorrect username or password!"))

    return render(request, 'login.html')

def signup_user(request):
    """User registration view that handles form submission for user signup"""
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()  # Save user and their profile data
            messages.success(request, _("Registration successful!"))
            return redirect('accounts:login')
        else:
            messages.error(request, _("Please correct the form errors"))
            return render(request, 'signup.html', {'form': form})

    form = SignUpForm()
    return render(request, 'signup.html', {'form': form})
@login_required
def dashboard(request):
    """User Dashboard with quick stats and app navigation"""
    
    # Quick statistics
    quick_stats = {
        'total_sales': 1247,
        'total_inventory': 856,
        'active_containers': 23,
        'pending_expenses': 45,
    }

    # App navigation setup - with direct URLs
    apps = [
        {
            'name': 'Daily Sales', 
            'url': '/daily_sale/dashboard/',  # URL مستقیم
            'icon': '💰', 
            'active': True,
            'description': 'Daily transactions and sales management'
        },
        {
            'name': 'Containers', 
            'url': '/containers/transactions/report/',  # URL مستقیم
            'icon': '🚢', 
            'active': True,
            'description': 'Container and shipping management'
        },
        {
            'name': 'Expenses', 
            'url': '/expenses/home_expenses/',  # URL مستقیم
            'icon': '💸', 
            'active': True,
            'description': 'Expense tracking and management'
        },
        {
            'name': 'Employees', 
            'url': '/employee/overview/',  # URL مستقیم
            'icon': '👥', 
            'active': True,
            'description': 'Employee and staff management'
        },
        {
            'name': 'Finance', 
            'url': '/finance/home_finance/',  # URL مستقیم
            'icon': '📊', 
            'active': True,
            'description': 'Financial reports and analysis'
        },
        {
            'name': 'Reports', 
            'url': '/reports/home_reports/',  # URL مستقیم
            'icon': '📋', 
            'active': True,
            'description': 'Comprehensive reporting system'
        },
    ]

    context = {
        'quick_stats': quick_stats,
        'apps': apps
    }
    return render(request, 'dashboard.html', context)


def logout_user(request):
	logout(request)
	messages.success(request, "You Have Been Logged Out...")
	return redirect('accounts:home')

def update_user(request):
    if request.user.is_authenticated: #ابتدا بررسی می‌کنیم که آیا کاربر وارد شده است یا خیر.
        current_user = User.objects.get(id=request.user.id) # استفاده از request.user.is_authenticated برای بررسی وضعیت ورود
        user_form = UserUpdateForm(request.POST or None, instance = current_user) # استفاده از فرم UserUpdateForm برای بروزرسانی داده‌ها
        if user_form.is_valid(): 
            user_form.save() # ذخیره‌سازی و بروزرسانی اطلاعات
            login(request, current_user) # بروزرسانی اطلاعات کاربر و ورود مجدد به سیستم
            messages.success(request, 'Updated!')
            return redirect('home')
        return render(request, 'update_user.html', {'user_form': user_form})
       
    else:
        messages.error(request, 'login First') # اگر کاربر وارد نشده باشد
        return redirect('home')
    
def update_password(request):
    if not request.user.is_authenticated:
        messages.error(request, _('please login first!'))
        return redirect('login')

    current_user = request.user

    if request.method == 'POST':
        form = UpdatePasswordForm(current_user, request.POST)
        if form.is_valid():
            form.save()
            login(request, current_user)
            messages.success(request, 'password changed successfuly!')
            return redirect('update_user')
        else:
            for error in list(form.errors.values()):
                messages.error(request, error)
    else:
        form = UpdatePasswordForm(current_user)

    return render(request, 'update_password.html', {'form': form})

def update_info(request):
    if not request.user.is_authenticated:
        messages.error(request, _('please login first'))
        return redirect('login')

    current_user, created = UserProfile.objects.get_or_create(user=request.user) # اطلاعات کاربر ساخته شده را ذخیره میکنیم تا در مراحل بعدی استفاده کنیم

    if request.method == "POST":
        form = UpdateUserInfo(request.POST, instance=current_user)
        if form.is_valid():
            form.save()
            messages.success(request, _(' ')) 
            return redirect('home')
        else:
            messages.error(request, _('Error'))
    else:
        form = UpdateUserInfo(instance=current_user) # نمایش یک فرم خالی برای کاربر و وارد کردن اطلاعات

    return render(request, 'update_info.html', {'form': form})