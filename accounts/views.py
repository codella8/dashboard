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

def my_view(request):
    print("Current language:", get_language())

def admin_only(user): #بررسی اینکه کاربر ادمین هست یا نه
    return user.is_staff 

@user_passes_test(admin_only) #فقط به ادمین‌ها اجازه ورود می‌دهد
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
    if request.user.is_authenticated:
        messages.info(request, _("you logged in once!"))
        return redirect("accounts:dashboard")  # 🔥 استفاده از نام URL

    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            
            # 🔥 استفاده از نام URL به جای آدرس مستقیم
            next_page = request.GET.get('next', 'accounts:dashboard')
            
            if '/admin/' in next_page and not user.is_staff:
                messages.error(request, _("you don not have access to admin panel"))
                return redirect('accounts:dashboard')
                
            return redirect('accounts:dashboard')
        else:
            messages.error(request, _("incorrect email or password!"))
    
    return render(request, 'login.html')
 
def signup_user(request):
    if request.method == "POST": # بررسی درخواست از نوع post
        form = SignUpForm(request.POST)
        if form.is_valid(): #فرم وارد شده را اعتبارسنجی می‌کنیم
            username = form.cleaned_data['username']
            email = form.cleaned_data['email']

        messages.error(request, _("please correct forms errors!")) #در صورتی که فرم معتبر نباشد
        return render(request, 'signup.html', {'form': form})

    else:
        form = SignUpForm()
    return render(request, 'signup.html', {'form': form})

# accounts/views.py
@login_required
def dashboard(request):
    # 📊 آمار سریع
    try:
        total_sales = DailySaleTransaction.objects.filter(transaction_type='sale').count()
    except:
        total_sales = 0
    
    try:
        active_containers = Container.objects.filter(status='in_transit').count()
    except:
        active_containers = 0
    
    try:
        total_inventory = Inventory_List.objects.count()
    except:
        total_inventory = 0
    
    try:
        pending_expenses = ExpenseItem.objects.filter(status='pending').count()
    except:
        pending_expenses = 0

    quick_stats = {
        'total_sales': total_sales,
        'active_containers': active_containers,
        'total_inventory': total_inventory,
        'pending_expenses': pending_expenses,
    }
    
    # 🚀 لیست اپ‌ها - فقط اپ‌هایی که مطمئن هستیم کار می‌کنند
    apps = [
        {
            'name': 'فروش روزانه',
            'url': 'daily_sale:dashboard',
            'icon': '📈',
            'color': 'success',
            'description': 'مدیریت فروش روزانه و تراکنش‌ها',
            'active': True
        },
        {
            'name': 'مدیریت موجودی',
            'url': 'inventory:dashboard',
            'icon': '📦', 
            'color': 'primary',
            'description': 'مدیریت موجودی و انبار',
            'active': False  # موقتاً غیرفعال
        },
        {
            'name': 'کانتینرها',
            'url': 'containers:saraf_list',
            'icon': '🚢',
            'color': 'info',
            'description': 'پیگیری کانتینرها و محموله‌ها',
            'active': True
        },
        {
            'name': 'امور مالی',
            'url': 'finance:dashboard',
            'icon': '💰',
            'color': 'warning',
            'description': 'گزارش‌های مالی و حسابداری',
            'active': False
        },
        {
            'name': 'هزینه‌ها',
            'url': 'expenses:dashboard',
            'icon': '💸',
            'color': 'danger',
            'description': 'مدیریت هزینه‌ها و مخارج', 
            'active': False
        },
        {
            'name': 'کارمندان',
            'url': 'employee:dashboard',
            'icon': '👥',
            'color': 'secondary',
            'description': 'مدیریت پرسنل و حقوق',
            'active': False
        },
        {
            'name': 'حساب کاربری',
            'url': 'accounts:dashboard', 
            'icon': '👤',
            'color': 'dark',
            'description': 'مدیریت کاربران و پروفایل',
            'active': True
        },
        {
            'name': 'گزارش‌ها',
            'url': 'reports:dashboard',
            'icon': '📊',
            'color': 'light',
            'description': 'گزارش‌های جامع و آنالیز',
            'active': False
        },
    ]
    
    context = {
        'quick_stats': quick_stats,
        'apps': apps,
    }
    
    return render(request, 'dashboard.html', context)

@login_required
def home_dashboard(request):
    """صفحه اصلی - می‌تونی به داشبورد ریدایرکت کنی یا صفحه جدا بسازی"""
    return dashboard(request)

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