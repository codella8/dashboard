# daily_sale/utils.py
import logging
from decimal import Decimal
from datetime import timedelta
from django.db import transaction as db_transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone
from .models import DailySaleTransaction, Payment, DailySummary, OutstandingCustomer

logger = logging.getLogger(__name__)

# ---------------------------
# Aggregation helpers (اصلاح‌شده)
# ---------------------------
def _aggregate_transactions(qs, tx_type=None):
    """Aggregate total, count, items for a queryset of transactions"""
    if tx_type:
        qs = qs.filter(transaction_type=tx_type)
    
    # فقط فیلدهایی که همیشه وجود دارند را aggregate می‌کنیم
    result = qs.aggregate(
        total=Sum('total_amount'),
        count=Count('id'),
    )
    
    # اگر نوع تراکنش sale باشد، items_sold را هم محاسبه می‌کنیم
    if tx_type == 'sale':
        items_sold_result = qs.aggregate(
            items_sold=Sum('quantity')
        )
        result['items_sold'] = items_sold_result['items_sold']
    else:
        result['items_sold'] = None
    
    return result

# ---------------------------
# Sales summary for a range
# ---------------------------
def get_sales_summary(start_date, end_date):
    try:
        sales_agg = _aggregate_transactions(DailySaleTransaction.objects.filter(date__range=[start_date, end_date]), 'sale')
        purchase_agg = _aggregate_transactions(DailySaleTransaction.objects.filter(date__range=[start_date, end_date]), 'purchase')

        total_sales = sales_agg['total'] or Decimal('0.00')
        total_purchases = purchase_agg['total'] or Decimal('0.00')
        net_revenue = total_sales - total_purchases

        return {
            'total_sales': total_sales,
            'total_purchases': total_purchases,
            'net_revenue': net_revenue,
            'transactions_count': sales_agg['count'] or 0,
            'items_sold': sales_agg['items_sold'] or 0,
        }
    except Exception as e:
        logger.exception("Error in get_sales_summary")
        return {'total_sales': 0, 'total_purchases': 0, 'net_revenue': 0, 'transactions_count': 0, 'items_sold': 0}

# ---------------------------
# Timeseries helpers
# ---------------------------
def sales_timeseries(start_date, end_date, group_by='day'):
    try:
        if DailySummary.objects.filter(date__range=[start_date, end_date]).exists():
            return _timeseries_from_summary(start_date, end_date)
        return _timeseries_from_transactions(start_date, end_date)
    except Exception:
        logger.exception("Error in sales_timeseries")
        return []

def _timeseries_from_summary(start_date, end_date):
    summaries = DailySummary.objects.filter(date__range=[start_date, end_date]).order_by('date')
    return [
        {
            'date': s.date,
            'total_sales': s.total_sales,
            'total_purchases': s.total_purchases,
            'transactions_count': s.transactions_count,
            'items_sold': s.items_sold,
        } for s in summaries
    ]

def _timeseries_from_transactions(start_date, end_date):
    timeseries = []
    delta = end_date - start_date
    for i in range(delta.days + 1):
        current_date = start_date + timedelta(days=i)
        sales_agg = _aggregate_transactions(DailySaleTransaction.objects.filter(date=current_date), 'sale')
        purchase_agg = _aggregate_transactions(DailySaleTransaction.objects.filter(date=current_date), 'purchase')
        timeseries.append({
            'date': current_date,
            'total_sales': sales_agg['total'] or Decimal('0.00'),
            'total_purchases': purchase_agg['total'] or Decimal('0.00'),
            'transactions_count': sales_agg['count'] or 0,
            'items_sold': sales_agg['items_sold'] or 0,
        })
    return timeseries

# ---------------------------
# Daily summary recompute (اصلاح‌شده)
# ---------------------------
def recompute_daily_summary_for_date(target_date):
    if not target_date:
        logger.warning("recompute_daily_summary_for_date called with no date")
        return None

    logger.info(f"Recomputing DailySummary for {target_date}")
    try:
        with db_transaction.atomic():
            transactions = DailySaleTransaction.objects.filter(date=target_date)
            if not transactions.exists():
                DailySummary.objects.filter(date=target_date).delete()
                return None

            sales_agg = _aggregate_transactions(transactions, 'sale')
            purchase_agg = _aggregate_transactions(transactions, 'purchase')

            total_sales = sales_agg['total'] or Decimal('0.00')
            total_purchases = purchase_agg['total'] or Decimal('0.00')
            transactions_count = transactions.count()
            items_sold = sales_agg['items_sold'] or 0
            customers_count = transactions.filter(transaction_type='sale').values('customer').distinct().count()
            total_profit = total_sales - total_purchases
            payments_total = Payment.objects.filter(date=target_date).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            net_balance = total_sales - payments_total
            
            # محاسبه آمار اضافی
            total_tax = transactions.aggregate(total=Sum('tax_amount'))['total'] or Decimal('0.00')
            total_discount = transactions.aggregate(total=Sum('discount'))['total'] or Decimal('0.00')
            total_paid = transactions.aggregate(total=Sum('advance'))['total'] or Decimal('0.00')
            
            paid_transactions = transactions.filter(payment_status='paid').count()
            partial_transactions = transactions.filter(payment_status='partial').count()
            unpaid_transactions = transactions.filter(payment_status='unpaid').count()
            
            total_outstanding = transactions.filter(balance__gt=0).aggregate(
                total=Sum('balance')
            )['total'] or Decimal('0.00')
            
            avg_transaction_value = Decimal('0.00')
            if transactions_count > 0:
                avg_transaction_value = total_sales / transactions_count

            # استفاده از update_or_create با UUID
            summary, created = DailySummary.objects.update_or_create(
                date=target_date,
                defaults={
                    'total_sales': total_sales,
                    'total_purchases': total_purchases,
                    'total_profit': total_profit,
                    'net_balance': net_balance,
                    'transactions_count': transactions_count,
                    'items_sold': items_sold,
                    'customers_count': customers_count,
                    'total_tax': total_tax,
                    'total_discount': total_discount,
                    'total_paid': total_paid,
                    'paid_transactions': paid_transactions,
                    'partial_transactions': partial_transactions,
                    'unpaid_transactions': unpaid_transactions,
                    'total_outstanding': total_outstanding,
                    'avg_transaction_value': avg_transaction_value,
                    'updated_at': timezone.now(),
                    'is_final': False,
                }
            )
            logger.info(f"{'Created' if created else 'Updated'} summary for {target_date}")
            logger.info(f"   Sales: {total_sales:,.2f} AED")
            logger.info(f"   Outstanding: {total_outstanding:,.2f} AED")
            logger.info(f"   Items: {items_sold}")
            return summary
    except Exception as e:
        logger.exception(f"Error in recompute_daily_summary_for_date: {e}")
        return None

# ---------------------------
# Outstanding recompute (اصلاح‌شده)
# ---------------------------
def recompute_outstanding_for_customer(customer_id):
    if not customer_id:
        logger.warning("recompute_outstanding_for_customer called with no customer_id")
        return

    try:
        with db_transaction.atomic():
            transactions = DailySaleTransaction.objects.filter(customer_id=customer_id)
            if not transactions.exists():
                OutstandingCustomer.objects.filter(customer_id=customer_id).delete()
                return

            total_debt = Decimal('0.00')
            tx_count = 0
            last_tx_date = None
            
            for tx in transactions:
                if tx.balance > Decimal('0.00'):
                    total_debt += tx.balance
                    tx_count += 1
                    if last_tx_date is None or tx.date > last_tx_date:
                        last_tx_date = tx.date

            if total_debt > Decimal('0.00'):
                OutstandingCustomer.objects.update_or_create(
                    customer_id=customer_id,
                    defaults={
                        'total_debt': total_debt,
                        'transactions_count': tx_count,
                        'last_transaction': last_tx_date,
                        'updated_at': timezone.now(),
                    }
                )
                logger.info(f"Updated outstanding for customer {customer_id}: {total_debt:,.2f} AED")
            else:
                OutstandingCustomer.objects.filter(customer_id=customer_id).delete()
                logger.info(f"Removed outstanding for customer {customer_id} (no debt)")

    except Exception as e:
        logger.exception(f"Error in recompute_outstanding_for_customer {customer_id}: {e}")

# ---------------------------
# Wrapper functions
# ---------------------------
def generate_daily_summaries_for_range(start_date, end_date):
    success = error = 0
    for i in range((end_date - start_date).days + 1):
        if recompute_daily_summary_for_date(start_date + timedelta(days=i)):
            success += 1
        else:
            error += 1
    logger.info(f"Generated {success} summaries, {error} errors")
    return success, error

def recompute_all_summaries(start_date=None, end_date=None):
    qs = DailySaleTransaction.objects.all()
    if start_date: qs = qs.filter(date__gte=start_date)
    if end_date: qs = qs.filter(date__lte=end_date)
    dates = qs.values_list('date', flat=True).distinct()
    success = error = 0
    for d in dates:
        if recompute_daily_summary_for_date(d):
            success += 1
        else:
            error += 1
    logger.info(f"Recompute complete: {success} success, {error} errors")
    return success, error