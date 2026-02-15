# employees/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q, Sum, Count, Avg, Max, F, Min
from django.db.models.functions import TruncMonth
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.contrib import messages
from reportlab.pdfgen import canvas
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, timedelta, date
from .models import Employee, SalaryPayment, EmployeeExpense
from accounts.models import UserProfile
from .forms import EmployeeForm,  SalaryPaymentForm
from .report import calculate_employee_financials
from django.http import HttpResponse
from io import BytesIO
import math

@login_required
@permission_required('employees.view_employee', raise_exception=True)
def employee_list(request):
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', 'all')
    employment_type = request.GET.get('type', 'all')
    sort_by = request.GET.get('sort', '-created_at')
    page_number = request.GET.get('page', 4)

    employees = Employee.objects.filter(is_active=True).select_related(
        'employee__user'
    ).prefetch_related(
        'salary_payments',
        'expenses'
    )
    
    if search_query:
        employees = employees.filter(
            Q(employee__user__first_name__icontains=search_query) |
            Q(employee__user__last_name__icontains=search_query) |
            Q(employee__user__email__icontains=search_query) |
            Q(position__icontains=search_query) |
            Q(employee__user__username__icontains=search_query)
        )
    
    if employment_type and employment_type != 'all':
        employees = employees.filter(employment_type=employment_type)
    
    if status_filter and status_filter != 'all':
        if status_filter == 'paid':
            employees = employees.filter(
                Q(total_paid__gte=F('salary_due')) |
                Q(total_paid__gte=F('salary_due') - F('debt_to_company'))
            )
        elif status_filter == 'partial':
            employees = employees.filter(
                Q(total_paid__gt=0) &
                Q(total_paid__lt=F('salary_due') - F('debt_to_company'))
            )
        elif status_filter == 'unpaid':
            employees = employees.filter(total_paid=0)
    
    # مرتب‌سازی
    if sort_by == 'name':
        employees = employees.order_by('employee__user__last_name', 'employee__user__first_name')
    elif sort_by == '-name':
        employees = employees.order_by('-employee__user__last_name', '-employee__user__first_name')
    elif sort_by == 'salary':
        employees = employees.order_by('salary_due')
    elif sort_by == '-salary':
        employees = employees.order_by('-salary_due')
    elif sort_by == 'hire_date':
        employees = employees.order_by('hire_date')
    elif sort_by == '-hire_date':
        employees = employees.order_by('-hire_date')
    else:  # پیش‌فرض
        employees = employees.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(employees, 25)
    page_obj = paginator.get_page(page_number)
    
    # آماده‌سازی داده‌های کارمندان
    employees_data = []
    for emp in page_obj:
        # محاسبات مالی
        total_paid = emp.total_paid
        total_expenses = emp.total_expenses
        remaining_balance = emp.remaining_salary
        
        # وضعیت پرداخت
        if remaining_balance <= 0:
            payment_status = {
                'label': 'Paid',
                'color': 'success',
                'icon': 'check-circle',
                'badge_class': 'status-paid'
            }
            payment_progress = 100
        elif total_paid > 0:
            payment_status = {
                'label': 'Partial',
                'color': 'warning',
                'icon': 'exclamation-circle',
                'badge_class': 'status-partial'
            }
            if emp.salary_due > 0:
                payment_progress = (total_paid / emp.salary_due * 100)
            else:
                payment_progress = 0
        else:
            payment_status = {
                'label': 'Unpaid',
                'color': 'danger',
                'icon': 'times-circle',
                'badge_class': 'status-unpaid'
            }
            payment_progress = 0
        
        # سال‌های خدمت
        years_of_service = None
        if emp.hire_date:
            today = date.today()
            if emp.termination_date:
                end_date = emp.termination_date
            else:
                end_date = today
            
            total_days = (end_date - emp.hire_date).days
            years_of_service = math.floor(total_days / 365.25)
        
        employees_data.append({
            'employee': emp,
            'financials': {
                'total_paid': total_paid,
                'total_expenses': total_expenses,
                'remaining_balance': remaining_balance,
                'debt_to_company': emp.debt_to_company,
                'salary_due': emp.salary_due,
                'payment_percentage': payment_progress,
                'is_fully_paid': remaining_balance <= 0,
            },
            'payment_status': payment_status,
            'payment_progress': round(payment_progress, 1),
            'years_of_service': years_of_service,
        })
    
    # آمار کلی
    active_employees = Employee.objects.filter(is_active=True)
    total_salary = active_employees.aggregate(
        total=Sum('salary_due')
    )['total'] or Decimal('0')
    
    total_paid = SalaryPayment.objects.filter(
        is_paid=True,
        employee__is_active=True
    ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
    
    total_expenses = EmployeeExpense.objects.filter(
        employee__is_active=True
    ).aggregate(total=Sum('price'))['total'] or Decimal('0')
    
    total_debt = active_employees.aggregate(
        total=Sum('debt_to_company')
    )['total'] or Decimal('0')
    
    total_stats = {
        'active_employees': active_employees.count(),
        'total_salary': total_salary,
        'total_paid': total_paid,
        'total_expenses': total_expenses,
        'total_debt': total_debt,
        'total_remaining': total_salary - total_paid - total_expenses - total_debt,
        'avg_salary': active_employees.aggregate(
            avg=Avg('salary_due')
        )['avg'] or Decimal('0'),
    }
    payment_status_stats = {
        'paid': 0,
        'partial': 0,
        'unpaid': 0,
    }
    
    for emp in active_employees:
        if emp.remaining_salary <= 0:
            payment_status_stats['paid'] += 1
        elif emp.total_paid > 0:
            payment_status_stats['partial'] += 1
        else:
            payment_status_stats['unpaid'] += 1
    
    context = {
        'employees_data': employees_data,
        'page_obj': page_obj,
        'total_stats': total_stats,
        'payment_status_stats': payment_status_stats,
        'filters': {
            'search': search_query,
            'status': status_filter,
            'type': employment_type,
            'sort': sort_by,
        },
        'sort_options': [
            ('-created_at', 'Newest First'),
            ('created_at', 'Oldest First'),
            ('name', 'Name A-Z'),
            ('-name', 'Name Z-A'),
            ('salary', 'Salary Low-High'),
            ('-salary', 'Salary High-Low'),
            ('hire_date', 'Oldest Hires'),
            ('-hire_date', 'Newest Hires'),
        ],
        'status_options': [
            ('all', 'All Status'),
            ('paid', 'Paid'),
            ('partial', 'Partial'),
            ('unpaid', 'Unpaid'),
        ],
        'type_options': [
            ('all', 'All Types'),
            ('full_time', 'Full Time'),
            ('part_time', 'Part Time'),
            ('freelance', 'Freelance'),
        ],
    }
    
    return render(request, 'employee/employee_list.html', context)

@login_required
def employee_quick_view(request, employee_id):
    employee = get_object_or_404(Employee, id=employee_id)   
    financials = calculate_employee_financials(employee)
    recent_payments = employee.salary_payments.filter(
        is_paid=True
    ).order_by('-date')[:5]
    recent_expenses = employee.expenses.all().order_by('-date')[:5]
    data = {
        'id': str(employee.id),
        'name': employee.employee.user.get_full_name() if employee.employee and employee.employee.user else 'Unknown',
        'position': employee.position or 'Not specified',
        'email': employee.employee.user.email if employee.employee and employee.employee.user else '',
        'phone': employee.employee.phone if employee.employee else '',
        'hire_date': employee.hire_date.strftime('%Y-%m-%d') if employee.hire_date else '',
        'salary_due': str(employee.salary_due),
        'financials': {
            'total_paid': str(financials.get('total_paid', 0)),
            'total_expenses': str(financials.get('total_expenses', 0)),
            'remaining_balance': str(financials.get('remaining_balance', 0)),
            'payment_percentage': financials.get('payment_percentage', 0),
        },
        'recent_payments': [
            {
                'date': p.date.strftime('%Y-%m-%d'),
                'amount': str(p.salary_amount),
                'method': p.get_payment_method_display(),
            }
            for p in recent_payments
        ],
        'recent_expenses': [
            {
                'date': e.date.strftime('%Y-%m-%d'),
                'expense': e.expense,
                'amount': str(e.price),
                'category': e.get_category_display(),
            }
            for e in recent_expenses
        ],
        'status': 'paid' if financials.get('is_fully_paid', False) else 'partial' if financials.get('total_paid', 0) > 0 else 'unpaid',
    }
    return JsonResponse(data)

@login_required
@permission_required('employees.view_employee', raise_exception=True)
def employee_detail(request, pk):
    employee = get_object_or_404(
        Employee.objects.select_related(
            'employee__user'
        ).prefetch_related(
            'salary_payments',
            'expenses'
        ),
        id=pk
    )
    
    # محاسبات مالی دقیق
    total_paid = employee.total_paid
    total_expenses = employee.total_expenses
    remaining_balance = employee.remaining_salary
    
    # اطلاعات کامل مالی
    financials = {
        'total_paid': total_paid,
        'total_expenses': total_expenses,
        'debt_to_company': employee.debt_to_company,
        'salary_due': employee.salary_due,
        'remaining_balance': remaining_balance,
        'payment_percentage': (total_paid / employee.salary_due * 100) if employee.salary_due > 0 else 0,
        'is_fully_paid': remaining_balance <= 0,
        'net_salary': employee.salary_due - total_expenses - employee.debt_to_company,
    }
    
    # آمار پرداخت‌ها
    salary_payments = employee.salary_payments.all().order_by('-date')
    recent_payments = salary_payments[:10]
    
    payment_stats = {
        'total_payments': salary_payments.count(),
        'paid_count': salary_payments.filter(is_paid=True).count(),
        'pending_count': salary_payments.filter(is_paid=False).count(),
        'total_paid_amount': salary_payments.filter(is_paid=True).aggregate(
            total=Sum('salary_amount')
        )['total'] or Decimal('0'),
        'total_pending_amount': salary_payments.filter(is_paid=False).aggregate(
            total=Sum('salary_amount')
        )['total'] or Decimal('0'),
        'avg_payment_amount': salary_payments.filter(is_paid=True).aggregate(
            avg=Avg('salary_amount')
        )['avg'] or Decimal('0'),
        'largest_payment': salary_payments.filter(is_paid=True).aggregate(
            max=Max('salary_amount')
        )['max'] or Decimal('0'),
        'smallest_payment': salary_payments.filter(is_paid=True).aggregate(
            min=Min('salary_amount')
        )['min'] or Decimal('0'),
        'last_payment_date': salary_payments.filter(is_paid=True).order_by('-date').first(),
        'first_payment_date': salary_payments.filter(is_paid=True).order_by('date').first(),
        'payment_method_distribution': salary_payments.values('payment_method').annotate(
            count=Count('id'),
            total=Sum('salary_amount')
        ).order_by('-total'),
    }
    
    # آمار هزینه‌ها
    expenses = employee.expenses.all().order_by('-date')
    recent_expenses = expenses[:10]
    
    expense_stats = {
        'total_expenses': expenses.count(),
        'total_amount': expenses.aggregate(total=Sum('price'))['total'] or Decimal('0'),
        'avg_expense': expenses.aggregate(avg=Avg('price'))['avg'] or Decimal('0'),
        'largest_expense': expenses.aggregate(max=Max('price'))['max'] or Decimal('0'),
        'smallest_expense': expenses.aggregate(min=Min('price'))['min'] or Decimal('0'),
        'by_category': expenses.values('category').annotate(
            total=Sum('price'),
            count=Count('id')
        ).order_by('-total'),
        'monthly_expenses': expenses.annotate(
            month=TruncMonth('date')
        ).values('month').annotate(
            total=Sum('price'),
            count=Count('id')
        ).order_by('-month')[:6],
    }
    
    user = employee.employee.user if employee.employee and employee.employee.user else None
    
    years_of_service = None
    months_of_service = None
    total_days_of_service = None
    
    if employee.hire_date:
        today = date.today()
        start_date = employee.hire_date
        end_date = employee.termination_date if employee.termination_date else today
        
        total_days = (end_date - start_date).days
        total_days_of_service = total_days
        
        # محاسبه دقیق سال و ماه
        years_of_service = total_days // 365
        remaining_days = total_days % 365
        months_of_service = remaining_days // 30
    
    # وضعیت پرداخت
    if remaining_balance <= 0:
        payment_status = {
            'label': 'Paid in Full',
            'color': 'success',
            'icon': 'check-circle',
            'class': 'status-paid',
            'description': 'All salary and expenses are paid'
        }
    elif total_paid > 0:
        payment_status = {
            'label': 'Partial Payment',
            'color': 'warning',
            'icon': 'exclamation-circle',
            'class': 'status-partial',
            'description': f'{financials["payment_percentage"]:.1f}% of salary paid'
        }
    else:
        payment_status = {
            'label': 'Unpaid',
            'color': 'danger',
            'icon': 'times-circle',
            'class': 'status-unpaid',
            'description': 'No payments made yet'
        }
    
    # سلامت مالی
    if remaining_balance <= 0:
        financial_health = 'excellent'
    elif remaining_balance <= employee.salary_due * Decimal('0.3'):
        financial_health = 'good'
    elif remaining_balance <= employee.salary_due * Decimal('0.6'):
        financial_health = 'fair'
    else:
        financial_health = 'poor'
    
    financials['financial_health'] = financial_health
    
    payment_trend_data = []
    for i in range(11, -1, -1):
        month_date = date.today().replace(day=1) - timedelta(days=30*i)
        month_start = month_date.replace(day=1)
        
        if i == 0:
            month_end = date.today()
        else:
            next_month = month_start.replace(day=28) + timedelta(days=4)
            month_end = next_month - timedelta(days=next_month.day)
        
        month_payments = salary_payments.filter(
            date__range=[month_start, month_end],
            is_paid=True
        ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
        
        month_expenses = expenses.filter(
            date__range=[month_start, month_end]
        ).aggregate(total=Sum('price'))['total'] or Decimal('0')
        
        payment_trend_data.append({
            'month': month_start.strftime('%b'),
            'year': month_start.year,
            'full_month': month_start.strftime('%B %Y'),
            'payments_amount': month_payments,
            'expenses_amount': month_expenses,
            'payment_count': salary_payments.filter(
                date__range=[month_start, month_end],
                is_paid=True
            ).count(),
            'expense_count': expenses.filter(
                date__range=[month_start, month_end]
            ).count(),
            'month_start': month_start,
        })
    
    current_year = date.today().year
    yearly_stats = []
    
    for year in range(current_year - 2, current_year + 1):
        year_payments = salary_payments.filter(
            date__year=year,
            is_paid=True
        ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
        
        year_expenses = expenses.filter(
            date__year=year
        ).aggregate(total=Sum('price'))['total'] or Decimal('0')
        
        yearly_stats.append({
            'year': year,
            'total_payments': year_payments,
            'total_expenses': year_expenses,
            'net_amount': year_payments - year_expenses,
            'payment_count': salary_payments.filter(date__year=year, is_paid=True).count(),
            'expense_count': expenses.filter(date__year=year).count(),
        })
    
    quick_summary = {
        'total_earned': total_paid,
        'total_deducted': total_expenses + employee.debt_to_company,
        'net_earned': total_paid - total_expenses - employee.debt_to_company,
        'current_month_payments': salary_payments.filter(
            date__month=date.today().month,
            date__year=date.today().year,
            is_paid=True
        ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0'),
        'current_month_expenses': expenses.filter(
            date__month=date.today().month,
            date__year=date.today().year
        ).aggregate(total=Sum('price'))['total'] or Decimal('0'),
        'pending_payments_count': salary_payments.filter(is_paid=False).count(),
    }
    
    employee_info = {
        'full_name': user.get_full_name() if user else 'Unknown Employee',
        'first_name': user.first_name if user else '',
        'last_name': user.last_name if user else '',
        'email': user.email if user else '',
        'username': user.username if user else '',
        'position': employee.position or 'Not specified',
        'employment_type': employee.get_employment_type_display(),
        'hire_date': employee.hire_date,
        'termination_date': employee.termination_date,
        'years_of_service': years_of_service,
        'months_of_service': months_of_service,
        'days_of_service': total_days_of_service,
        'status': 'Active' if employee.is_active else 'Inactive',
        'salary_due': employee.salary_due,
        'debt_to_company': employee.debt_to_company,
        'notes': employee.note,
        'avatar_initials': (user.first_name[0] + user.last_name[0]).upper() if user and user.first_name and user.last_name else '?',
        'is_current': not employee.termination_date or employee.termination_date >= date.today(),
    }
    
    context = {
        'employee': employee,
        'employee_info': employee_info,
        'financials': financials,
        'payment_status': payment_status,
        'salary_payments': salary_payments[:50],  # محدود کردن برای نمایش
        'expenses': expenses[:50],  # محدود کردن برای نمایش
        'payment_stats': payment_stats,
        'expense_stats': expense_stats,
        'recent_payments': recent_payments,
        'recent_expenses': recent_expenses,
        'payment_trend_data': payment_trend_data,
        'yearly_stats': yearly_stats,
        'quick_summary': quick_summary,
        'today': date.today(),
        'current_year': current_year,
    }
    
    return render(request, 'employee/employee_detail.html', context)

def calculate_advanced_financials(employee):
    today = date.today()
    
    current_year_payments = employee.salary_payments.filter(
        date__year=today.year,
        is_paid=True
    ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
    
    current_year_expenses = employee.expenses.filter(
        date__year=today.year
    ).aggregate(total=Sum('price'))['total'] or Decimal('0')
    
    # میانگین ماهانه
    months_active = 12
    if employee.hire_date:
        hire_year = employee.hire_date.year
        hire_month = employee.hire_date.month
        
        if hire_year == today.year:
            months_active = today.month - hire_month + 1
        elif hire_year < today.year:
            months_active = 12
    
    avg_monthly_payment = current_year_payments / months_active if months_active > 0 else Decimal('0')
    avg_monthly_expense = current_year_expenses / months_active if months_active > 0 else Decimal('0')
    
    return {
        'current_year_payments': current_year_payments,
        'current_year_expenses': current_year_expenses,
        'avg_monthly_payment': avg_monthly_payment,
        'avg_monthly_expense': avg_monthly_expense,
        'months_active_this_year': months_active,
    }
    
@login_required
@permission_required('employees.add_salarypayment', raise_exception=True)
def process_salary_payment(request):
    today = timezone.now().date()
    search_query = request.GET.get('search', '').strip()
    selected_employee_id = request.GET.get('employee', '')
    form = SalaryPaymentForm()
    selected_employee = None
    remaining_balance = Decimal('0')
    if selected_employee_id:
        try:
            selected_employee = Employee.objects.get(id=selected_employee_id, is_active=True)
            total_paid = selected_employee.salary_payments.filter(
                is_paid=True
            ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
            
            total_advances = selected_employee.expenses.aggregate(
                total=Sum('price')
            )['total'] or Decimal('0')
            
            remaining_balance = selected_employee.salary_due - total_paid - total_advances
            form = SalaryPaymentForm(initial={
                'employee': selected_employee,
                'date': today,
                'salary_amount': max(remaining_balance, Decimal('0')),
                'is_paid': True,
                'payment_method': 'bank_transfer',
            })
            
        except Employee.DoesNotExist:
            messages.error(request, 'Selected employee not found')
    if request.method == 'POST':
        form = SalaryPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.is_paid = True
            total_paid = payment.employee.salary_payments.filter(
                is_paid=True
            ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
            
            total_advances = payment.employee.expenses.aggregate(
                total=Sum('price')
            )['total'] or Decimal('0')
            
            max_payable = payment.employee.salary_due - total_paid - total_advances
            
            if payment.salary_amount > max_payable:
                messages.error(request, 
                    f'Amount exceeds maximum payable amount (${max_payable})')
            else:
                payment.save()
                employee_name = payment.employee.employee.user.get_full_name() if payment.employee.employee and payment.employee.employee.user else 'Unknown'
                messages.success(request, 
                    f'Payment of ${payment.salary_amount} processed for {employee_name}')
                return redirect('employee:payment_invoice', payment_id=payment.id)
        else:
            messages.error(request, 'Please check the form for errors')

    existing_employees = Employee.objects.filter(is_active=True).values_list('employee_id', flat=True)
    user_profiles = UserProfile.objects.filter(
        user__is_active=True,
        id__in=existing_employees
    ).select_related('user')
    if search_query:
        user_profiles = user_profiles.filter(
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query) |
            Q(user__email__icontains=search_query)
        )
    employees_data = []
    for user_profile in user_profiles:
        try:
            emp = Employee.objects.get(
                employee=user_profile,
                is_active=True
            )
            total_paid = emp.salary_payments.filter(
                is_paid=True
            ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
            
            total_advances = emp.expenses.aggregate(
                total=Sum('price')
            )['total'] or Decimal('0')
            
            remaining = emp.salary_due - total_paid - total_advances
            if remaining <= 0:
                status = 'paid'
                status_label = 'Paid'
                status_color = 'success'
                status_icon = 'check-circle'
            elif remaining == emp.salary_due:
                status = 'unpaid'
                status_label = 'Unpaid'
                status_color = 'danger'
                status_icon = 'times-circle'
            else:
                status = 'partial'
                status_label = 'Partial'
                status_color = 'warning'
                status_icon = 'exclamation-circle'
            
            employees_data.append({
                'id': emp.id,
                'employee': emp,
                'user_profile': user_profile,
                'salary_due': emp.salary_due,
                'total_paid': total_paid,
                'total_advances': total_advances,
                'remaining': max(remaining, Decimal('0')),
                'status': status,
                'status_label': status_label,
                'status_color': status_color,
                'status_icon': status_icon,
                'department': emp.department.name if emp.department else 'No Department',
                'position': emp.position or 'Not specified',
                'is_selected': selected_employee_id == str(emp.id),
                'last_payment': emp.salary_payments.filter(
                    is_paid=True
                ).order_by('-date').first(),
            })
            
        except Employee.DoesNotExist:
            continue
    stats = {
        'total_employees': len(employees_data),
        'total_payable': sum([e['remaining'] for e in employees_data]),
        'paid_count': len([e for e in employees_data if e['status'] == 'paid']),
        'unpaid_count': len([e for e in employees_data if e['status'] == 'unpaid']),
        'partial_count': len([e for e in employees_data if e['status'] == 'partial']),
    }
    context = {
        'employees_data': employees_data,
        'form': form,
        'selected_employee': selected_employee,
        'remaining_balance': remaining_balance,
        'stats': stats,
        'today': today.strftime('%Y-%m-%d'),
        'filters': {
            'search': search_query,
            'employee': selected_employee_id,
        },
    }
    return render(request, 'employees/process_payment.html', context)

@login_required
def payment_invoice(request, payment_id):
    try:
        payment = get_object_or_404(
            SalaryPayment.objects.select_related(
                'employee__employee__user',
                'employee__department'
            ),
            id=payment_id
        )
        total_paid_until_now = payment.employee.salary_payments.filter(
            is_paid=True,
            date__lte=payment.date
        ).aggregate(total=Sum('salary_amount'))['total'] or Decimal('0')
        
        total_advances = payment.employee.expenses.aggregate(
            total=Sum('price')
        )['total'] or Decimal('0')
        
        remaining_balance = payment.employee.salary_due - total_paid_until_now - total_advances
        
        context = {
            'payment': payment,
            'employee': payment.employee,
            'total_paid_until_now': total_paid_until_now,
            'total_advances': total_advances,
            'remaining_balance': remaining_balance,
            'company_name': 'Your Company Name',
            'company_address': '123 Business Street, City, Country',
            'company_phone': '+1 (123) 456-7890',
            'company_email': 'accounts@company.com',
            'invoice_date': timezone.now().date(),
            'invoice_number': f"INV-{payment.date.strftime('%Y%m')}-{str(payment.id)[:8]}",
        }
        
        return render(request, 'employees/payment_invoice.html', context)
        
    except Exception as e:
        messages.error(request, f'Error loading invoice: {str(e)}')
        return redirect('employee:process_salary_payment')


@login_required
def download_payment_pdf(request, payment_id):
    try:
        payment = get_object_or_404(
            SalaryPayment.objects.select_related(
                'employee__employee__user',
                'employee__department'
            ),
            id=payment_id
        )  
        buffer = BytesIO()
        p = canvas.Canvas(buffer)
        p.drawString(100, 800, f"Payment Invoice - {payment.employee.employee.user.get_full_name()}")
        p.drawString(100, 780, f"Payment Amount: ${payment.salary_amount}")
        p.drawString(100, 760, f"Payment Date: {payment.date}")
        p.drawString(100, 740, f"Payment Method: {payment.get_payment_method_display()}")
        
        if payment.reference_number:
            p.drawString(100, 720, f"Reference: {payment.reference_number}")
        
        p.showPage()
        p.save()
        
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        filename = f"payment_{payment.date.strftime('%Y%m%d')}_{payment.id[:8]}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        messages.error(request, f'Error generating PDF: {str(e)}')
        return redirect('employee:payment_invoice', payment_id=payment_id)
 