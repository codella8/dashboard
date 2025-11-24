# employee/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden
from datetime import datetime, timedelta

from .models import Employee, SalaryPayment, EmployeeExpense
from . import report
from decimal import Decimal

DEC_ZERO = Decimal("0.00")


def _parse_date_param(val, default=None):
    if not val:
        return default
    if hasattr(val, 'year'):
        return val
    try:
        return datetime.fromisoformat(val).date()
    except Exception:
        try:
            return datetime.strptime(val, "%Y-%m-%d").date()
        except Exception:
            return default


def is_admin_user(user):
    return user.is_active and (user.is_staff or user.is_superuser)


@login_required
def employee_list_view(request):
    """
    List employees. If user has company on profile, only show that company's employees.
    Shows quick aggregates per employee (DB-annotated when possible).
    """
    company = getattr(getattr(request.user, "profile", None), "company", None)
    start = _parse_date_param(request.GET.get('start_date'), None)
    end = _parse_date_param(request.GET.get('end_date'), None)

    # use report.employees_overview which handles date filtering & company
    company_id = company.id if company else None
    employees = report.employees_overview(company_id=company_id, start_date=start, end_date=end, limit=500)

    context = {
        'employees': employees,
        'start_date': start,
        'end_date': end,
    }
    return render(request, "employee/employee_list.html", context)


@login_required
def employee_detail_view(request, pk):
    """
    Detail page with full financial summary, recent payments and expenses.
    """
    company = getattr(getattr(request.user, "profile", None), "company", None)
    emp = get_object_or_404(Employee.objects.select_related('employee'), pk=pk)
    # if company-scoped user, enforce
    if company and getattr(emp.employee, "company_id", None) != company.id:
        return HttpResponseForbidden("Not allowed")

    start = _parse_date_param(request.GET.get('start_date'), None)
    end = _parse_date_param(request.GET.get('end_date'), None)

    summary = report.employee_financial_summary(emp.pk, start_date=start, end_date=end)

    payments = SalaryPayment.objects.filter(employee=emp)
    expenses = EmployeeExpense.objects.filter(employee=emp)
    if start:
        payments = payments.filter(date__gte=start)
        expenses = expenses.filter(date__gte=start)
    if end:
        payments = payments.filter(date__lte=end)
        expenses = expenses.filter(date__lte=end)

    payments = payments.order_by('-date')[:200]
    expenses = expenses.order_by('-date')[:200]

    context = {
        'employee': emp,
        'summary': summary,
        'payments': payments,
        'expenses': expenses,
        'start_date': start,
        'end_date': end,
    }
    return render(request, "employee/employee_detail.html", context)


@login_required
@user_passes_test(is_admin_user)
def employees_financial_overview(request):
    """
    Admin-only overview across company (or all).
    Returns overall totals and top owed employees.
    """
    company = getattr(getattr(request.user, "profile", None), "company", None)
    start = _parse_date_param(request.GET.get('start_date'), None)
    end = _parse_date_param(request.GET.get('end_date'), None)

    company_id = company.id if company else None
    employees = report.employees_overview(company_id=company_id, start_date=start, end_date=end, limit=1000)

    # Compute global sums
    total_scheduled = sum(e['total_scheduled'] for e in employees) or DEC_ZERO
    total_paid = sum(e['total_paid'] for e in employees) or DEC_ZERO
    total_unpaid = sum(e['total_unpaid'] for e in employees) or DEC_ZERO
    total_expenses = sum(e['total_expenses'] for e in employees) or DEC_ZERO
    total_net = sum(e['net_payable'] for e in employees) or DEC_ZERO

    # top owed (sorted by net_payable desc)
    top_owed = sorted(employees, key=lambda x: x['net_payable'], reverse=True)[:20]

    context = {
        'employees': employees,
        'total_scheduled': total_scheduled,
        'total_paid': total_paid,
        'total_unpaid': total_unpaid,
        'total_expenses': total_expenses,
        'total_net': total_net,
        'top_owed': top_owed,
        'start_date': start,
        'end_date': end,
    }
    return render(request, "employee/employees_financial_overview.html", context)


# JSON endpoints for dashboards / charts
@login_required
def employee_timeseries_api(request, pk=None):
    """
    Return salary payments timeseries as JSON. If pk provided returns for single employee.
    ?days=N
    """
    days = int(request.GET.get('days', 30))
    if days <= 0 or days > 3650:
        days = 30
    data = report.salary_payments_timeseries(employee_id=pk, days=days)
    return JsonResponse({'status': 'success', 'series': data})
