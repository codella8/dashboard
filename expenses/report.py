from django.db.models import (
    Sum, Count, Avg, F, DecimalField, ExpressionWrapper
)
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import Expense


TOTAL_EXPR = ExpressionWrapper(
    F("quantity") * F("unit_price"),
    output_field=DecimalField(max_digits=14, decimal_places=2)
)


def expense_queryset(start_date=None, end_date=None):
    qs = Expense.objects.annotate(total=TOTAL_EXPR)

    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    return qs


def get_expense_summary(start_date=None, end_date=None):
    qs = expense_queryset(start_date, end_date)

    data = qs.aggregate(
        total_amount=Sum("total"),
        total_count=Count("id"),
        average_expense=Avg("total"),
    )

    return {
        "total_amount": data["total_amount"] or Decimal("0"),
        "total_count": data["total_count"],
        "average_expense": data["average_expense"] or Decimal("0"),
    }


def get_expenses_by_category(start_date=None, end_date=None):
    qs = expense_queryset(start_date, end_date)

    return qs.values(
        "category__name"
    ).annotate(
        total_amount=Sum("total"),
        count=Count("id")
    ).order_by("-total_amount")


def get_monthly_expenses(months=6):
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=months * 30)

    qs = expense_queryset(start_date, end_date)

    return qs.extra(
        select={
            "year": "EXTRACT(year FROM date)",
            "month": "EXTRACT(month FROM date)",
        }
    ).values("year", "month").annotate(
        total_amount=Sum("total"),
        count=Count("id")
    ).order_by("year", "month")
