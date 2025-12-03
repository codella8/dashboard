from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from .models import Employee, SalaryPayment, EmployeeExpense, Department


def calculate_employee_financials(employee):
    """محاسبات مالی برای یک کارمند"""
    total_paid = employee.salary_payments.filter(is_paid=True).aggregate(
        total=Sum('salary_amount')
    )['total'] or Decimal('0')
    
    total_expenses = employee.expenses.aggregate(
        total=Sum('price')
    )['total'] or Decimal('0')
    
    net_balance = employee.salary_due - total_paid - total_expenses - employee.debt_to_company
    
    return {
        'total_paid': total_paid,
        'total_expenses': total_expenses,
        'net_balance': net_balance,
        'is_fully_paid': net_balance <= 0,
        'remaining_balance': max(net_balance, Decimal('0'))
    }


def get_payroll_summary(start_date=None, end_date=None):
    """خلاصه حقوق و دستمزد"""
    qs = SalaryPayment.objects.all()

    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    summary = qs.aggregate(
        total_paid=Sum('salary_amount', filter=Q(is_paid=True)),
        total_pending=Sum('salary_amount', filter=Q(is_paid=False)),
        payment_count=Count('id'),
        paid_count=Count('id', filter=Q(is_paid=True)),
        pending_count=Count('id', filter=Q(is_paid=False)),
        avg_salary=Avg('salary_amount')
    )
    
    return summary


def get_department_stats():
    """آمار دپارتمان‌ها"""
    return Department.objects.annotate(
        employee_count=Count('employee', filter=Q(employee__is_active=True)),
        total_salary=Sum('employee__salary_due'),
        avg_salary=Avg('employee__salary_due')
    ).order_by('-employee_count')


def get_employee_performance(start_date=None, end_date=None):
    """عملکرد کارمندان"""
    employees = Employee.objects.filter(is_active=True)
    
    performance_data = []
    for employee in employees:
        financials = calculate_employee_financials(employee)
        
        # پرداخت‌های در بازه زمانی
        payments_in_period = employee.salary_payments.all()
        expenses_in_period = employee.expenses.all()
        
        if start_date:
            payments_in_period = payments_in_period.filter(date__gte=start_date)
            expenses_in_period = expenses_in_period.filter(date__gte=start_date)
        if end_date:
            payments_in_period = payments_in_period.filter(date__lte=end_date)
            expenses_in_period = expenses_in_period.filter(date__lte=end_date)
        
        period_payments = payments_in_period.aggregate(
            total=Sum('salary_amount', filter=Q(is_paid=True))
        )['total'] or Decimal('0')
        
        period_expenses = expenses_in_period.aggregate(
            total=Sum('price')
        )['total'] or Decimal('0')
        
        performance_data.append({
            'employee': employee,
            'financials': financials,
            'period_payments': period_payments,
            'period_expenses': period_expenses,
            'efficiency_score': (period_payments / employee.salary_due * 100) if employee.salary_due > 0 else 0
        })
    
    return sorted(performance_data, key=lambda x: x['efficiency_score'], reverse=True)


def get_expense_analysis(start_date=None, end_date=None):
    """تحلیل هزینه‌ها"""
    qs = EmployeeExpense.objects.all()

    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    # تحلیل بر اساس دسته‌بندی
    by_category = qs.values('category').annotate(
        total_amount=Sum('price'),
        expense_count=Count('id'),
        avg_amount=Avg('price')
    ).order_by('-total_amount')
    
    # تحلیل بر اساس کارمند
    by_employee = qs.values(
        'employee__employee__user__first_name',
        'employee__employee__user__last_name',
        'employee__department__name'
    ).annotate(
        total_amount=Sum('price'),
        expense_count=Count('id')
    ).order_by('-total_amount')
    
    # تحلیل ماهانه
    monthly_expenses = qs.extra(
        select={'year': 'EXTRACT(year FROM date)', 'month': 'EXTRACT(month FROM date)'}
    ).values('year', 'month').annotate(
        total_amount=Sum('price'),
        expense_count=Count('id')
    ).order_by('year', 'month')
    
    return {
        'by_category': by_category,
        'by_employee': by_employee,
        'monthly_expenses': monthly_expenses,
        'total_expenses': qs.aggregate(total=Sum('price'))['total'] or Decimal('0')
    }


def get_salary_trends(group_by='month'):
    """روند حقوق‌ها"""
    qs = SalaryPayment.objects.filter(is_paid=True)
    
    if group_by == 'month':
        return qs.extra(
            select={'year': 'EXTRACT(year FROM date)', 'month': 'EXTRACT(month FROM date)'}
        ).values('year', 'month').annotate(
            total_paid=Sum('salary_amount'),
            payment_count=Count('id'),
            avg_salary=Avg('salary_amount')
        ).order_by('year', 'month')
    
    else:  # روزانه
        return qs.values('date').annotate(
            total_paid=Sum('salary_amount'),
            payment_count=Count('id')
        ).order_by('date')


def get_employee_financial_status():
    """وضعیت مالی کارمندان"""
    employees = Employee.objects.filter(is_active=True)
    
    status_data = []
    for employee in employees:
        financials = calculate_employee_financials(employee)
        
        status_data.append({
            'employee': employee,
            'salary_due': employee.salary_due,
            'total_paid': financials['total_paid'],
            'total_expenses': financials['total_expenses'],
            'debt_to_company': employee.debt_to_company,
            'net_balance': financials['net_balance'],
            'status': 'Fully Paid' if financials['is_fully_paid'] else 'Pending',
            'payment_progress': (financials['total_paid'] / employee.salary_due * 100) if employee.salary_due > 0 else 0
        })
    
    return sorted(status_data, key=lambda x: x['net_balance'], reverse=True)


def get_upcoming_salary_payments(days=30):
    """پرداخت‌های حقوق آینده"""
    today = timezone.now().date()
    future_date = today + timedelta(days=days)
    
    employees = Employee.objects.filter(
        is_active=True,
        salary_due__gt=0
    )
    
    upcoming_payments = []
    for employee in employees:
        financials = calculate_employee_financials(employee)
        if financials['remaining_balance'] > 0:
            upcoming_payments.append({
                'employee': employee,
                'amount_due': financials['remaining_balance'],
                'due_status': 'Overdue' if today > employee.date else 'Upcoming'
            })
    
    return sorted(upcoming_payments, key=lambda x: x['amount_due'], reverse=True)