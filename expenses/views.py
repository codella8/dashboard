from django.shortcuts import render
from django.utils import timezone
from .report import (
    get_expense_summary,
    get_expenses_by_category,
    get_monthly_expenses,
)


def expense_dashboard(request):
    today = timezone.now().date()
    month_start = today.replace(day=1)

    context = {
        "summary": get_expense_summary(month_start, today),
        "category_data": get_expenses_by_category(month_start, today),
        "monthly_data": get_monthly_expenses(6),
    }

    return render(request, "expenses/dashboard.html", context)
