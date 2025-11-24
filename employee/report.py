# employee/report.py
from decimal import Decimal
from datetime import date, datetime, timedelta
from django.db.models import Sum, Count, Q, F, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Employee, SalaryPayment, EmployeeExpense

DEC_ZERO = Decimal("0.00")


def _parse_date(val, default=None):
    if not val:
        return default
    if hasattr(val, "year"):
        return val
    try:
        return datetime.fromisoformat(val).date()
    except Exception:
        try:
            return datetime.strptime(val, "%Y-%m-%d").date()
        except Exception:
            return default


def employee_financial_summary(employee_id, start_date=None, end_date=None):
    """
    Returns a dict summary for a single employee containing:
      - total_salary_due (sum of salary_amount scheduled in period)
      - total_salary_paid (sum of salary_amount where is_paid=True)
      - total_salary_unpaid (scheduled - paid)
      - total_expenses (sum of EmployeeExpense.price)
      - net_payable (total_salary_unpaid + total_expenses - debt_to_company)
      - payment_count, expense_count
    start_date/end_date can be date objects or 'YYYY-MM-DD' strings. If None -> whole history.
    """
    start = _parse_date(start_date, None)
    end = _parse_date(end_date, None)

    # base queryset filters
    payment_qs = SalaryPayment.objects.filter(employee_id=employee_id)
    expense_qs = EmployeeExpense.objects.filter(employee_id=employee_id)

    if start:
        payment_qs = payment_qs.filter(date__gte=start)
        expense_qs = expense_qs.filter(date__gte=start)
    if end:
        payment_qs = payment_qs.filter(date__lte=end)
        expense_qs = expense_qs.filter(date__lte=end)

    agg_payments = payment_qs.aggregate(
        total_scheduled=Coalesce(Sum('salary_amount'), Value(DEC_ZERO), output_field=DecimalField()),
        total_paid=Coalesce(Sum('salary_amount', filter=Q(is_paid=True)), Value(DEC_ZERO), output_field=DecimalField()),
        payment_count=Coalesce(Count('id'), Value(0)),
    )

    agg_expenses = expense_qs.aggregate(
        total_expenses=Coalesce(Sum('price'), Value(DEC_ZERO), output_field=DecimalField()),
        expense_count=Coalesce(Count('id'), Value(0)),
    )

    # try to get employee-level debt field (if present)
    try:
        emp = Employee.objects.only('debt_to_company').get(pk=employee_id)
        debt_to_company = emp.debt_to_company or DEC_ZERO
    except Employee.DoesNotExist:
        debt_to_company = DEC_ZERO

    total_scheduled = agg_payments['total_scheduled'] or DEC_ZERO
    total_paid = agg_payments['total_paid'] or DEC_ZERO
    total_unpaid = (total_scheduled - total_paid) if (total_scheduled and total_paid) else (total_scheduled - total_paid)
    total_expenses = agg_expenses['total_expenses'] or DEC_ZERO

    net_payable = (total_unpaid + total_expenses) - debt_to_company

    return {
        'employee_id': employee_id,
        'total_scheduled': total_scheduled,
        'total_paid': total_paid,
        'total_unpaid': total_unpaid,
        'total_expenses': total_expenses,
        'debt_to_company': debt_to_company,
        'net_payable': net_payable,
        'payment_count': int(agg_payments['payment_count'] or 0),
        'expense_count': int(agg_expenses['expense_count'] or 0),
        'period_start': start,
        'period_end': end,
    }


def employees_overview(company_id=None, start_date=None, end_date=None, limit=200):
    """
    Returns a list of employees with aggregated financials.
    If company_id provided, filters employees by their related UserProfile.company.
    """
    start = _parse_date(start_date, None)
    end = _parse_date(end_date, None)

    # Employee queryset, join to userprofile.employee__employee? Our Employee.employee -> UserProfile
    qs = Employee.objects.select_related('employee')

    if company_id:
        qs = qs.filter(employee__company_id=company_id)

    # Annotate using sub-aggregations on related models
    # Note: Django cannot easily annotate across filtered related sets with different filters,
    # so we'll aggregate global then narrow via filters on SalaryPayment/Expense in python as fallback for date ranges.
    if not start and not end:
        # simple annotate when no date filter: do in DB
        qs = qs.annotate(
            total_scheduled=Coalesce(Sum('salary_payments__salary_amount'), Value(DEC_ZERO), output_field=DecimalField()),
            total_paid=Coalesce(Sum('salary_payments__salary_amount', filter=Q(salary_payments__is_paid=True)), Value(DEC_ZERO), output_field=DecimalField()),
            total_expenses=Coalesce(Sum('expenses__price'), Value(DEC_ZERO), output_field=DecimalField()),
            payment_count=Coalesce(Count('salary_payments'), Value(0)),
            expense_count=Coalesce(Count('expenses'), Value(0)),
        ).order_by('-total_scheduled')[:limit]

        # convert to list of dicts
        out = []
        for e in qs:
            total_scheduled = e.total_scheduled or DEC_ZERO
            total_paid = e.total_paid or DEC_ZERO
            total_unpaid = total_scheduled - total_paid
            total_expenses = e.total_expenses or DEC_ZERO
            debt = e.debt_to_company or DEC_ZERO
            out.append({
                'employee_obj': e,
                'employee_id': e.pk,
                'name': str(e.employee) if e.employee else '—',
                'total_scheduled': total_scheduled,
                'total_paid': total_paid,
                'total_unpaid': total_unpaid,
                'total_expenses': total_expenses,
                'debt_to_company': debt,
                'net_payable': (total_unpaid + total_expenses) - debt,
                'payment_count': int(e.payment_count or 0),
                'expense_count': int(e.expense_count or 0),
            })
        return out

    # If date filters exist, compute per-employee by querying related sets (safer & accurate)
    employees = list(qs[:limit])
    out = []
    for e in employees:
        summary = employee_financial_summary(e.pk, start_date=start, end_date=end)
        emp_label = str(e.employee) if e.employee else '—'
        out.append({
            'employee_obj': e,
            'employee_id': e.pk,
            'name': emp_label,
            **summary
        })
    return out


def salary_payments_timeseries(employee_id=None, days=30):
    """
    Return timeseries (list of dict) of salary payments (paid/unpaid) for last `days` days.
    If employee_id is None, aggregate for all employees.
    """
    end = timezone.now().date()
    start = end - timedelta(days=days - 1)
    qs = SalaryPayment.objects.filter(date__range=[start, end])
    if employee_id:
        qs = qs.filter(employee_id=employee_id)

    series_qs = qs.values('date').annotate(
        scheduled=Coalesce(Sum('salary_amount'), Value(DEC_ZERO), output_field=DecimalField()),
        paid=Coalesce(Sum('salary_amount', filter=Q(is_paid=True)), Value(DEC_ZERO), output_field=DecimalField()),
        count=Coalesce(Count('id'), Value(0)),
    ).order_by('date')

    return [{'date': r['date'], 'scheduled': r['scheduled'], 'paid': r['paid'], 'count': int(r['count'])} for r in series_qs]
