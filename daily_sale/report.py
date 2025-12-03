from decimal import Decimal
from django.db.models import Sum, Count, Avg, F, Q, Max
from .models import DailySaleTransaction
from django.utils import timezone
from datetime import date

def parse_date_param(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except Exception:
        return None

def get_sales_summary(start_date=None, end_date=None):
    qs = DailySaleTransaction.objects.all()
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    agg = qs.aggregate(
        total_sales=Sum('total_amount', filter=Q(transaction_type='sale')),
        total_purchases=Sum('total_amount', filter=Q(transaction_type='purchase')),
        total_discount=Sum('discount'),
        total_tax=Sum('tax'),
        total_advance=Sum('advance'),
        total_qty=Sum('quantity'),
        total_transactions=Count('id'),
    )

    total_sales = agg.get('total_sales') or Decimal('0.00')
    total_purchases = agg.get('total_purchases') or Decimal('0.00')
    total_transactions = agg.get('total_transactions') or 0

    return {
        'total_sales': total_sales,
        'total_purchases': total_purchases,
        'net_revenue': total_sales - total_purchases,
        'total_transactions': total_transactions,
        'total_qty': agg.get('total_qty') or 0,
        'total_discount': agg.get('total_discount') or Decimal('0.00'),
        'total_tax': agg.get('total_tax') or Decimal('0.00'),
        'total_advance': agg.get('total_advance') or Decimal('0.00'),
    }

def sales_timeseries(start_date=None, end_date=None, group_by='day'):
    qs = DailySaleTransaction.objects.all()
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    if group_by == 'month':
        return qs.extra(select={'year': "EXTRACT(year FROM date)", 'month': "EXTRACT(month FROM date)"}).values('year','month').annotate(
            total_sales=Sum('total_amount', filter=Q(transaction_type='sale')),
            transaction_count=Count('id')
        ).order_by('year','month')
    else:
        return qs.values('date').annotate(
            total_sales=Sum('total_amount', filter=Q(transaction_type='sale')),
            total_purchases=Sum('total_amount', filter=Q(transaction_type='purchase')),
            transaction_count=Count('id'),
            items_sold=Sum('quantity', filter=Q(transaction_type='sale'))
        ).order_by('date')

def old_transactions(start_date=None, end_date=None):
    qs = DailySaleTransaction.objects.filter(status='pending', balance__gt=0)
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)

    agg = qs.values(
        'customer__id',
        'customer__user__first_name',
        'customer__user__last_name',
        'customer__user__email',
        'customer__phone',
    ).annotate(
        total_debt=Sum('balance'),
        transactions_count=Count('id'),
        last_transaction=Max('date')
    ).order_by('-total_debt')

    results = []
    for row in agg:
        results.append({
            'customer_id': row['customer__id'],
            'first_name': row.get('customer__user__first_name') or '',
            'last_name': row.get('customer__user__last_name') or '',
            'email': row.get('customer__user__email') or '',
            'phone': row.get('customer__phone') or '',
            'total_debt': row.get('total_debt') or Decimal('0.00'),
            'transactions_count': row.get('transactions_count') or 0,
            'last_transaction': row.get('last_transaction'),
        })
    return results
