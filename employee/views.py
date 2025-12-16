from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from django.db.models import Q, Count, Sum, Avg
from .models import Employee, SalaryPayment, EmployeeExpense, Department
from .report import (
    calculate_employee_financials,
    get_payroll_summary,
    get_department_stats,
    get_employee_performance,
    get_expense_analysis,
    get_salary_trends,
    get_employee_financial_status,
    get_upcoming_salary_payments
)


def employee_dashboard(request):
    """داشبورد مدیریت کارمندان"""
    today = timezone.now().date()
    
    # آمار کلی با فیلتر
    total_employees = Employee.objects.filter(is_active=True).count()
    total_departments = Department.objects.count()
    
    # خلاصه حقوق‌ها (آخرین 30 روز)
    thirty_days_ago = today - timedelta(days=30)
    payroll_summary = get_payroll_summary(thirty_days_ago, today)
    
    # پرداخت‌های آینده
    upcoming_payments = get_upcoming_salary_payments(30)
    
    # کارمندان اخیر (آخرین 10 نفر)
    recent_employees = Employee.objects.select_related(
        'employee', 'employee__user', 'department'
    ).order_by('-created_at')[:10]
    
    # محاسبات مالی برای کارمندان اخیر
    for emp in recent_employees:
        emp.financials = calculate_employee_financials(emp)
    
    context = {
        'total_employees': total_employees,
        'total_departments': total_departments,
        'payroll_summary': payroll_summary,
        'upcoming_payments': upcoming_payments[:5],
        'recent_employees': recent_employees,
        'today': today,
    }
    return render(request, 'employee/dashboard.html', context)


def employee_list(request):
    """لیست کارمندان با فیلترهای پیشرفته"""
    employees = Employee.objects.select_related(
        'employee', 'employee__user', 'department'
    ).filter(is_active=True)
    
    # فیلترهای پیشرفته
    filters = Q()
    
    # فیلتر دپارتمان
    department_id = request.GET.get('department')
    if department_id:
        filters &= Q(department_id=department_id)
    
    # فیلتر نوع استخدام
    employment_type = request.GET.get('employment_type')
    if employment_type:
        filters &= Q(employment_type=employment_type)
    
    # فیلتر وضعیت پرداخت
    payment_status = request.GET.get('payment_status')
    if payment_status == 'paid':
        # کارمندانی که حقوقشان کامل پرداخت شده
        employees = employees.annotate(
            total_paid=Sum('salary_payments__salary_amount', filter=Q(salary_payments__is_paid=True))
        ).filter(total_paid__gte=models.F('salary_due'))
    elif payment_status == 'unpaid':
        # کارمندانی که حقوقشان پرداخت نشده
        employees = employees.annotate(
            total_paid=Sum('salary_payments__salary_amount', filter=Q(salary_payments__is_paid=True))
        ).filter(Q(total_paid__lt=models.F('salary_due')) | Q(total_paid__isnull=True))
    
    # فیلتر بازه حقوق
    min_salary = request.GET.get('min_salary')
    max_salary = request.GET.get('max_salary')
    if min_salary:
        filters &= Q(salary_due__gte=min_salary)
    if max_salary:
        filters &= Q(salary_due__lte=max_salary)
    
    # فیلتر بازه تاریخ استخدام
    hire_start = request.GET.get('hire_start')
    hire_end = request.GET.get('hire_end')
    if hire_start:
        filters &= Q(hire_date__gte=hire_start)
    if hire_end:
        filters &= Q(hire_date__lte=hire_end)
    
    # فیلتر وضعیت فعال بودن
    is_active = request.GET.get('is_active')
    if is_active == 'true':
        filters &= Q(is_active=True)
    elif is_active == 'false':
        filters &= Q(is_active=False)
    
    # اعمال فیلترها
    employees = employees.filter(filters).order_by('-hire_date')
    
    # محاسبات مالی برای هر کارمند
    employee_list_with_financials = []
    for employee in employees:
        financials = calculate_employee_financials(employee)
        employee_list_with_financials.append({
            'employee': employee,
            'financials': financials
        })
    
    departments = Department.objects.all()
    
    context = {
        'employees_with_financials': employee_list_with_financials,
        'departments': departments,
        'filters': {
            'department': department_id,
            'employment_type': employment_type,
            'payment_status': payment_status,
            'min_salary': min_salary,
            'max_salary': max_salary,
            'hire_start': hire_start,
            'hire_end': hire_end,
            'is_active': is_active,
        }
    }
    return render(request, 'employee/employee_list.html', context)


def payroll_report(request):
    """گزارش حقوق و دستمزد با فیلترهای پیشرفته"""
    # تاریخ پیش‌فرض: آخرین 30 روز
    today = timezone.now().date()
    default_start = today - timedelta(days=30)
    
    # دریافت پارامترها
    start_date = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    
    # تبدیل به تاریخ
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    except:
        start_date = default_start
    
    try:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except:
        end_date = today
    
    # فیلترهای اضافی
    filters = Q(date__range=[start_date, end_date])
    
    department_id = request.GET.get('department')
    if department_id:
        filters &= Q(employee__department_id=department_id)
    
    payment_method = request.GET.get('payment_method')
    if payment_method:
        filters &= Q(payment_method=payment_method)
    
    payment_status = request.GET.get('payment_status')
    if payment_status == 'paid':
        filters &= Q(is_paid=True)
    elif payment_status == 'unpaid':
        filters &= Q(is_paid=False)
    
    # خلاصه حقوق با فیلتر
    payroll_summary = SalaryPayment.objects.filter(filters).aggregate(
        total_paid=Sum('salary_amount', filter=Q(is_paid=True)),
        total_pending=Sum('salary_amount', filter=Q(is_paid=False)),
        payment_count=Count('id'),
        paid_count=Count('id', filter=Q(is_paid=True)),
        pending_count=Count('id', filter=Q(is_paid=False)),
        avg_salary=Avg('salary_amount')
    )
    
    # پرداخت‌ها با فیلتر
    salary_payments = SalaryPayment.objects.select_related(
        'employee', 'employee__employee', 'employee__employee__user'
    ).filter(filters).order_by('-date')
    
    # روند حقوق ماهانه
    salary_trends = get_salary_trends('month')
    
    departments = Department.objects.all()
    
    context = {
        'payroll_summary': payroll_summary,
        'salary_payments': salary_payments,
        'salary_trends': salary_trends,
        'start_date': start_date,
        'end_date': end_date,
        'departments': departments,
        'filters': {
            'department': department_id,
            'payment_method': payment_method,
            'payment_status': payment_status,
        }
    }
    return render(request, 'employee/payroll_report.html', context)


def expense_report(request):
    """گزارش هزینه‌ها با فیلترهای پیشرفته"""
    # تاریخ پیش‌فرض: آخرین 30 روز
    today = timezone.now().date()
    default_start = today - timedelta(days=30)
    
    # دریافت پارامترها
    start_date = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    
    # تبدیل به تاریخ
    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    except:
        start_date = default_start
    
    try:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    except:
        end_date = today
    
    # فیلترهای اضافی
    filters = Q(date__range=[start_date, end_date])
    
    department_id = request.GET.get('department')
    if department_id:
        filters &= Q(employee__department_id=department_id)
    
    category = request.GET.get('category')
    if category:
        filters &= Q(category=category)
    
    min_amount = request.GET.get('min_amount')
    max_amount = request.GET.get('max_amount')
    if min_amount:
        filters &= Q(price__gte=min_amount)
    if max_amount:
        filters &= Q(price__lte=max_amount)
    
    # تحلیل هزینه‌ها با فیلتر
    qs = EmployeeExpense.objects.filter(filters)
    
    # تحلیل بر اساس دسته‌بندی
    by_category = qs.values('category').annotate(
        total_amount=Sum('price'),
        expense_count=Count('id'),
        avg_amount=Avg('price')
    ).order_by('-total_amount')
    
    # هزینه‌های جزئی
    expenses = EmployeeExpense.objects.select_related(
        'employee', 'employee__employee', 'employee__employee__user'
    ).filter(filters).order_by('-date')
    
    departments = Department.objects.all()
    
    context = {
        'expense_analysis': {
            'by_category': by_category,
            'total_expenses': qs.aggregate(total=Sum('price'))['total'] or Decimal('0')
        },
        'expenses': expenses,
        'start_date': start_date,
        'end_date': end_date,
        'departments': departments,
        'filters': {
            'department': department_id,
            'category': category,
            'min_amount': min_amount,
            'max_amount': max_amount,
        }
    }
    return render(request, 'employee/expense_report.html', context)


def financial_status(request):
    """وضعیت مالی کارمندان با فیلتر"""
    # فیلتر دپارتمان
    department_id = request.GET.get('department')
    
    # دریافت داده‌ها با فیلتر
    employees = Employee.objects.filter(is_active=True)
    
    if department_id:
        employees = employees.filter(department_id=department_id)
    
    financial_status_data = []
    total_salary_due = Decimal('0')
    total_paid = Decimal('0')
    total_balance = Decimal('0')
    
    for employee in employees:
        financials = calculate_employee_financials(employee)
        
        item = {
            'employee': employee,
            'salary_due': employee.salary_due,
            'total_paid': financials['total_paid'],
            'total_expenses': financials['total_expenses'],
            'debt_to_company': employee.debt_to_company,
            'net_balance': financials['net_balance'],
            'status': 'Fully Paid' if financials['is_fully_paid'] else 'Pending',
            'payment_progress': (financials['total_paid'] / employee.salary_due * 100) if employee.salary_due > 0 else 0
        }
        
        financial_status_data.append(item)
        
        # جمع‌آوری آمار
        total_salary_due += employee.salary_due
        total_paid += financials['total_paid']
        total_balance += financials['net_balance']
    
    # مرتب‌سازی
    sort_by = request.GET.get('sort', 'net_balance')
    reverse = request.GET.get('order', 'desc') == 'desc'
    
    financial_status_data.sort(
        key=lambda x: x[sort_by], 
        reverse=reverse
    )
    
    departments = Department.objects.all()
    
    context = {
        'financial_status_data': financial_status_data,
        'total_salary_due': total_salary_due,
        'total_paid': total_paid,
        'total_balance': total_balance,
        'departments': departments,
        'filters': {
            'department': department_id,
            'sort': sort_by,
            'order': 'desc' if reverse else 'asc',
        }
    }
    return render(request, 'employee/financial_status.html', context)


def department_analysis(request):
    """تحلیل دپارتمان‌ها با فیلتر"""
    # فیلتر تاریخ
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        except:
            start_date = None
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except:
            end_date = None
    
    # آمار دپارتمان‌ها
    department_stats = Department.objects.annotate(
        employee_count=Count('employee', filter=Q(employee__is_active=True)),
        total_salary=Sum('employee__salary_due'),
        avg_salary=Avg('employee__salary_due')
    ).order_by('-employee_count')
    
    # عملکرد کارمندان با فیلتر تاریخ
    employee_performance = get_employee_performance(start_date, end_date)
    
    context = {
        'department_stats': department_stats,
        'employee_performance': employee_performance[:10],  # 10 کارمند برتر
        'filters': {
            'start_date': start_date,
            'end_date': end_date,
        }
    }
    return render(request, 'employee/department_analysis.html', context)


def employee_detail(request, employee_id):
    """جزئیات کارمند"""
    employee = get_object_or_404(
        Employee.objects.select_related(
            'employee', 'employee__user', 'department'
        ), 
        id=employee_id
    )
    
    # فیلتر بازه تاریخ برای گزارش‌ها
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        except:
            start_date = None
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except:
            end_date = None
    
    # محاسبات مالی
    financials = calculate_employee_financials(employee)
    
    # پرداخت‌های حقوق با فیلتر
    payment_filters = Q(employee=employee)
    if start_date:
        payment_filters &= Q(date__gte=start_date)
    if end_date:
        payment_filters &= Q(date__lte=end_date)
    
    salary_payments = SalaryPayment.objects.filter(payment_filters).order_by('-date')
    
    # هزینه‌ها با فیلتر
    expense_filters = Q(employee=employee)
    if start_date:
        expense_filters &= Q(date__gte=start_date)
    if end_date:
        expense_filters &= Q(date__lte=end_date)
    
    expenses = EmployeeExpense.objects.filter(expense_filters).order_by('-date')
    
    context = {
        'employee': employee,
        'financials': financials,
        'salary_payments': salary_payments,
        'expenses': expenses,
        'filters': {
            'start_date': start_date,
            'end_date': end_date,
        }
    }
    return render(request, 'employee/employee_detail.html', context)