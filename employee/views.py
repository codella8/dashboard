from django.shortcuts import render
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
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
    
    # آمار کلی
    total_employees = Employee.objects.filter(is_active=True).count()
    total_departments = Department.objects.count()
    
    # خلاصه حقوق‌ها
    payroll_summary = get_payroll_summary()
    
    # پرداخت‌های آینده
    upcoming_payments = get_upcoming_salary_payments(30)
    
    # کارمندان اخیر
    recent_employees = Employee.objects.select_related(
        'employee', 'employee__user', 'department'
    ).order_by('-created_at')[:10]
    
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
    """لیست کارمندان"""
    employees = Employee.objects.select_related(
        'employee', 'employee__user', 'department'
    ).filter(is_active=True)
    
    # فیلترها
    department_id = request.GET.get('department')
    employment_type = request.GET.get('employment_type')
    
    if department_id:
        employees = employees.filter(department_id=department_id)
    if employment_type:
        employees = employees.filter(employment_type=employment_type)
    
    # محاسبات مالی برای هر کارمند
    for employee in employees:
        employee.financials = calculate_employee_financials(employee)
    
    departments = Department.objects.all()
    
    context = {
        'employees': employees,
        'departments': departments,
        'filters': {
            'department': department_id,
            'employment_type': employment_type,
        }
    }
    return render(request, 'employee/employee_list.html', context)


def payroll_report(request):
    """گزارش حقوق و دستمزد"""
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if not start_date:
        start_date = timezone.now().date() - timedelta(days=30)
    if not end_date:
        end_date = timezone.now().date()
    
    # خلاصه حقوق
    payroll_summary = get_payroll_summary(start_date, end_date)
    
    # پرداخت‌ها
    salary_payments = SalaryPayment.objects.select_related(
        'employee', 'employee__employee', 'employee__employee__user'
    ).filter(date__range=[start_date, end_date])
    
    # روند حقوق
    salary_trends = get_salary_trends('month')
    
    context = {
        'payroll_summary': payroll_summary,
        'salary_payments': salary_payments,
        'salary_trends': salary_trends,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'employee/payroll_report.html', context)


def expense_report(request):
    """گزارش هزینه‌ها"""
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if not start_date:
        start_date = timezone.now().date() - timedelta(days=30)
    if not end_date:
        end_date = timezone.now().date()
    
    # تحلیل هزینه‌ها
    expense_analysis = get_expense_analysis(start_date, end_date)
    
    # هزینه‌های جزئی
    expenses = EmployeeExpense.objects.select_related(
        'employee', 'employee__employee', 'employee__employee__user'
    ).filter(date__range=[start_date, end_date])
    
    context = {
        'expense_analysis': expense_analysis,
        'expenses': expenses,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'employee/expense_report.html', context)


def financial_status(request):
    """وضعیت مالی کارمندان"""
    financial_status_data = get_employee_financial_status()
    
    # آمار کلی
    total_salary_due = sum(item['salary_due'] for item in financial_status_data)
    total_paid = sum(item['total_paid'] for item in financial_status_data)
    total_balance = sum(item['net_balance'] for item in financial_status_data)
    
    context = {
        'financial_status_data': financial_status_data,
        'total_salary_due': total_salary_due,
        'total_paid': total_paid,
        'total_balance': total_balance,
    }
    return render(request, 'employee/financial_status.html', context)


def department_analysis(request):
    """تحلیل دپارتمان‌ها"""
    department_stats = get_department_stats()
    
    # عملکرد کارمندان
    employee_performance = get_employee_performance()
    
    context = {
        'department_stats': department_stats,
        'employee_performance': employee_performance[:10],  # 10 کارمند برتر
    }
    return render(request, 'employee/department_analysis.html', context)


def employee_detail(request, employee_id):
    """جزئیات کارمند"""
    from django.shortcuts import get_object_or_404
    
    employee = get_object_or_404(
        Employee.objects.select_related(
            'employee', 'employee__user', 'department'
        ), 
        id=employee_id
    )
    
    # محاسبات مالی
    financials = calculate_employee_financials(employee)
    
    # پرداخت‌های حقوق
    salary_payments = employee.salary_payments.all().order_by('-date')
    
    # هزینه‌ها
    expenses = employee.expenses.all().order_by('-date')
    
    context = {
        'employee': employee,
        'financials': financials,
        'salary_payments': salary_payments,
        'expenses': expenses,
    }
    return render(request, 'employee/employee_detail.html', context)