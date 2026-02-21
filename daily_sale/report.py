# daily_sale/report.py
from decimal import Decimal
from datetime import date
from django.db.models import Sum, Count, Q
from .models import (
    DailySaleTransaction,
    OutstandingCustomer,
)

def parse_date_param(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
    
def get_sales_summary(start_date=None, end_date=None):
    qs = DailySaleTransaction.objects.all()

    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    agg = qs.aggregate(
        total_sales=Sum("total_amount", filter=Q(transaction_type="sale")),
        total_purchases=Sum("total_amount", filter=Q(transaction_type="purchase")),
        total_returns=Sum("total_amount", filter=Q(transaction_type="return")),
        transactions_count=Count("id"),
        items_sold=Sum("quantity", filter=Q(transaction_type="sale")),
    )

    total_sales = agg["total_sales"] or Decimal("0.00")
    total_purchases = agg["total_purchases"] or Decimal("0.00")
    total_returns = agg["total_returns"] or Decimal("0.00")

    return {
        "total_sales": total_sales,
        "total_purchases": total_purchases,
        "total_returns": total_returns,
        "net_revenue": total_sales - total_purchases - total_returns,
        "transactions_count": agg["transactions_count"] or 0,
        "items_sold": agg["items_sold"] or 0,
    }

def sales_timeseries(start_date=None, end_date=None, group_by="day"):
    qs = DailySaleTransaction.objects.all()

    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    if group_by == "month":
        return (
            qs.annotate(
                year=Q("date__year"),
                month=Q("date__month"),
            )
            .values("year", "month")
            .annotate(
                total_sales=Sum("total_amount", filter=Q(transaction_type="sale")),
                total_purchases=Sum("total_amount", filter=Q(transaction_type="purchase")),
                total_returns=Sum("total_amount", filter=Q(transaction_type="return")),
                transaction_count=Count("id"),
                items_sold=Sum("quantity", filter=Q(transaction_type="sale")),
            )
            .order_by("year", "month")
        )

    return (
        qs.values("date")
        .annotate(
            total_sales=Sum("total_amount", filter=Q(transaction_type="sale")),
            total_purchases=Sum("total_amount", filter=Q(transaction_type="purchase")),
            total_returns=Sum("total_amount", filter=Q(transaction_type="return")),
            transaction_count=Count("id"),
            items_sold=Sum("quantity", filter=Q(transaction_type="sale")),
            customers_count=Count("customer", distinct=True),
        )
        .order_by("-date")
    )

def outstanding_list():
    return (
        OutstandingCustomer.objects
        .select_related("customer__user")
        .filter(total_debt__gt=0)
        .order_by("-total_debt")
    )
