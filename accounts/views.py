from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from daily_sale.models import DailySaleTransaction
from containers.models import Container
from .forms import SignUpForm, UserUpdateForm, UpdatePasswordForm
from django.contrib.auth.models import User
from django.utils.translation import gettext as _
from functools import wraps
from .models import Product

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

def home(request):    
    products = Product.objects.all()
    return render(request, 'home.html', {'products': products})

def login_user(request):

    if request.user.is_authenticated:
        messages.info(request, _("You are already logged in!"))
        
        if request.user.is_staff:
            return redirect("accounts:dashboard")
        else:
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
                
                next_page = request.GET.get('next')

                if user.is_staff:
                    if next_page and '/admin/' in next_page:
                        return redirect(next_page)
                    return redirect('accounts:dashboard')

                else:
                    if next_page and ('/admin/' in next_page or '/dashboard/' in next_page):
                        messages.warning(request, _("Access denied. Redirecting to your profile."))
                        return redirect('daily_sale:customer_detail')
                    return redirect('daily_sale:customer_detail')
            else:
                messages.error(request, _("Incorrect username or password!"))

    return render(request, 'login.html')


def signup_user(request):
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

def product(request, pk):
    product = get_object_or_404(Product, id=pk) 
    return render(request, 'product.html', { 
        'product': product,
    })

@login_required
@admin_required
def dashboard(request):
    try:
        total_sales = DailySaleTransaction.objects.count()
    except:
        total_sales = 0 
    
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
        'total_containers': total_containers,
        'total_users': total_users,
    }
    
    apps = [
        {
            'name': 'Daily Sales', 
            'url': 'daily_sale:transaction_list',
            'icon': 'fas fa-shopping-cart', 
            'description': 'Daily transactions and sales management'
        },
        {
            'name': 'Containers', 
            'url': 'containers:list',
            'icon': 'fas fa-shipping-fast', 
            'description': 'Container and shipping management'
        },
        {
            'name': 'Expenses', 
            'url': 'expenses:report/', 
            'icon': 'fas fa-money-bill-wave', 
            'description': 'Expense tracking and management'
        },
        {
            'name': 'Employees', 
            'url': 'employee:list/', 
            'icon': 'fas fa-users',  
            'description': 'Employee and staff management'
        },

        {
            'name': 'Reports', 
            'url': '#',  
            'icon': 'fas fa-file-alt', 
            'description': 'Comprehensive reporting system'
        },
    ]

    context = {
        'quick_stats': quick_stats,
        'apps': apps
    }
    return render(request, 'dashboard.html', context)

@login_required
@admin_required
def admin_panel(request):
    return redirect('admin:index')

def logout_user(request):
    logout(request)
    messages.success(request, _("You Have Been Logged Out..."))
    return redirect('accounts:home')

@login_required
def update_user(request):
    current_user = request.user 
    user_form = UserUpdateForm(request.POST or None, instance=current_user)
    
    if request.method == "POST":
        if user_form.is_valid(): 
            user_form.save()
            messages.success(request, _('Profile updated successfully!'))
            return redirect('accounts:home')
    
    return render(request, 'update_user.html', {'user_form': user_form})

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


@login_required
def user_home(request):
    context = {
        'user': request.user,
        'is_admin': request.user.is_staff
    }
    return render(request, 'home.html', context)