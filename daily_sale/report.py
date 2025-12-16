# daily_sale/report.py
from decimal import Decimal
from django.db.models import Sum, Count, Q
from .models import DailySaleTransaction, DailySummary, OutstandingCustomer
from datetime import date

def parse_date_param(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except Exception:
        return None

def get_sales_summary(start_date=None, end_date=None):
    """خلاصه فروش برای یک دوره"""
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
    
    total_sales = agg.get("total_sales") or Decimal("0.00")
    total_purchases = agg.get("total_purchases") or Decimal("0.00")
    total_returns = agg.get("total_returns") or Decimal("0.00")
    
    return {
        "total_sales": total_sales,
        "total_purchases": total_purchases,
        "total_returns": total_returns,
        "net_revenue": total_sales - total_purchases - total_returns,
        "transactions_count": agg.get("transactions_count") or 0,
        "items_sold": agg.get("items_sold") or 0,
    }

def sales_timeseries(start_date=None, end_date=None, group_by="day"):
    """سری زمانی فروش"""
    qs = DailySaleTransaction.objects.all()
    
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)
    
    if group_by == "month":
        return qs.extra(
            select={
                "year": "EXTRACT(year FROM date)",
                "month": "EXTRACT(month FROM date)"
            }
        ).values("year", "month").annotate(
            total_sales=Sum("total_amount", filter=Q(transaction_type="sale")),
            total_purchases=Sum("total_amount", filter=Q(transaction_type="purchase")),
            total_returns=Sum("total_amount", filter=Q(transaction_type="return")),
            transaction_count=Count("id"),
            items_sold=Sum("quantity", filter=Q(transaction_type="sale")),
        ).order_by("year", "month")
    
    else:  # group_by == "day"
        return qs.values("date").annotate(
            total_sales=Sum("total_amount", filter=Q(transaction_type="sale")),
            total_purchases=Sum("total_amount", filter=Q(transaction_type="purchase")),
            total_returns=Sum("total_amount", filter=Q(transaction_type="return")),
            transaction_count=Count("id"),
            items_sold=Sum("quantity", filter=Q(transaction_type="sale")),
            customers_count=Count("customer", distinct=True),
        ).order_by("-date")


def outstanding_list(start_date=None, end_date=None):
    try:
        if start_date is None and end_date is None:
            return OutstandingCustomer.objects.select_related("customer__user").order_by("-total_debt")
    except Exception:
        pass
    # fallback heavy compute (safe)
    from .utils import recompute_outstanding_for_customer
    customers = DailySaleTransaction.objects.values_list("customer_id", flat=True).distinct()
    results = []
    for cid in customers:
        if not cid:
            continue
        # compute per-customer
        from .models import DailySaleTransaction, Payment
        txs = DailySaleTransaction.objects.filter(customer_id=cid)
        total_debt = Decimal("0.00")
        tx_count = 0
        last_tx = None
        for tx in txs:
            paid = Payment.objects.filter(transaction=tx).aggregate(p=Sum("amount"))["p"] or Decimal("0.00")
            remaining = (tx.total_amount or Decimal("0.00")) - paid
            if remaining and remaining > 0:
                total_debt += remaining
                tx_count += 1
                if not last_tx or (tx.date and tx.date > last_tx):
                    last_tx = tx.date
        if total_debt > 0:
            results.append({
                "customer_id": cid,
                "total_debt": total_debt,
                "transactions_count": tx_count,
                "last_transaction": last_tx,
            })
    return sorted(results, key=lambda x: x["total_debt"], reverse=True)
