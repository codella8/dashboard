# daily_sale/utils.py
from decimal import Decimal
from django.db import transaction as db_transaction
import logging
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import OutstandingCustomer
from .models import DailySaleTransaction, Payment, DailySummary

logger = logging.getLogger(__name__)
def get_sales_summary(start_date, end_date):
    try:
        sales_data = DailySaleTransaction.objects.filter(
            date__range=[start_date, end_date],
            transaction_type='sale'
        ).aggregate(
            total_sales=Sum('total_amount'),
            items_sold=Sum('quantity'),
            transactions_count=Count('id')
        )
        purchases_data = DailySaleTransaction.objects.filter(
            date__range=[start_date, end_date],
            transaction_type='purchase'
        ).aggregate(
            total_purchases=Sum('total_amount'),
            count=Count('id')
        )
        
        total_sales = sales_data['total_sales'] or Decimal('0.00')
        total_purchases = purchases_data['total_purchases'] or Decimal('0.00')
        net_revenue = total_sales - total_purchases
        
        return {
            'total_sales': total_sales,
            'total_purchases': total_purchases,
            'net_revenue': net_revenue,
            'transactions_count': sales_data['transactions_count'] or 0,
            'items_sold': sales_data['items_sold'] or 0,
        }
    except Exception as e:
        logger.error(f"Error in get_sales_summary: {e}")
        return {
            'total_sales': Decimal('0.00'),
            'total_purchases': Decimal('0.00'),
            'net_revenue': Decimal('0.00'),
            'transactions_count': 0,
            'items_sold': 0,
        }


def sales_timeseries(start_date, end_date, group_by="day"):
    try:
        if DailySummary.objects.filter(
            date__range=[start_date, end_date]
        ).exists():
            return sales_timeseries_from_summary(start_date, end_date, group_by)
        return sales_timeseries_from_transactions(start_date, end_date, group_by)
        
    except Exception as e:
        logger.error(f"Error in sales_timeseries: {e}")
        return []


def sales_timeseries_from_summary(start_date, end_date, group_by="day"):
    try:
        summaries = DailySummary.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('date')
        
        timeseries = []
        for summary in summaries:
            timeseries.append({
                'date': summary.date,
                'total_sales': summary.total_sales,
                'total_purchases': summary.total_purchases,
                'transactions_count': summary.transactions_count,
                'items_sold': summary.items_sold,
            })
        
        return timeseries
    except Exception as e:
        logger.error(f"Error in sales_timeseries_from_summary: {e}")
        return []


def sales_timeseries_from_transactions(start_date, end_date, group_by="day"):
    try:
        delta = end_date - start_date
        timeseries = []
        
        for i in range(delta.days + 1):
            current_date = start_date + timedelta(days=i)
            
            daily_sales = DailySaleTransaction.objects.filter(
                date=current_date,
                transaction_type='sale'
            ).aggregate(
                total_sales=Sum('total_amount'),
                items_sold=Sum('quantity'),
                transactions_count=Count('id')
            )
            
            daily_purchases = DailySaleTransaction.objects.filter(
                date=current_date,
                transaction_type='purchase'
            ).aggregate(
                total_purchases=Sum('total_amount'),
                count=Count('id')
            )
            
            timeseries.append({
                'date': current_date,
                'total_sales': daily_sales['total_sales'] or Decimal('0.00'),
                'total_purchases': daily_purchases['total_purchases'] or Decimal('0.00'),
                'transactions_count': daily_sales['transactions_count'] or 0,
                'items_sold': daily_sales['items_sold'] or 0,
            })
        
        return timeseries
    except Exception as e:
        logger.error(f"Error in sales_timeseries_from_transactions: {e}")
        return []


def recompute_daily_summary_for_date(target_date):
    if not target_date:
        logger.warning("recompute_daily_summary_for_date called with no date")
        return None
    
    logger.info(f" Recomputing daily summary for date: {target_date}")
    
    try:
        with transaction.atomic():
            transactions = DailySaleTransaction.objects.filter(date=target_date)
            if not transactions.exists():
                DailySummary.objects.filter(date=target_date).delete()
                logger.info(f"✅ No transactions for {target_date}, summary removed")
                return None
            agg_data = transactions.aggregate(
                total_sales=Sum('total_amount', filter=Q(transaction_type='sale')),
                total_purchases=Sum('total_amount', filter=Q(transaction_type='purchase')),
                transactions_count=Count('id'),
                items_sold=Sum('quantity', filter=Q(transaction_type='sale')),
                customers_count=Count('customer', distinct=True, filter=Q(transaction_type='sale')),
            )
            total_sales = agg_data.get('total_sales') or Decimal('0.00')
            total_purchases = agg_data.get('total_purchases') or Decimal('0.00')
            transactions_count = agg_data.get('transactions_count') or 0
            items_sold = agg_data.get('items_sold') or 0
            customers_count = agg_data.get('customers_count') or 0
            total_profit = total_sales - total_purchases
            payments_total = Payment.objects.filter(
                date=target_date
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            net_balance = total_sales - payments_total
            defaults = {
                'total_sales': total_sales,
                'total_purchases': total_purchases,
                'total_profit': total_profit,
                'net_balance': net_balance,
                'transactions_count': transactions_count,
                'items_sold': items_sold,
                'customers_count': customers_count,
                'updated_at': timezone.now(),
                'is_final': False,
            }
            
            summary, created = DailySummary.objects.update_or_create(
                date=target_date,
                defaults=defaults
            )
            
            if created:
                logger.info(f"✅ Created new summary for {target_date}")
            else:
                logger.info(f"📝 Updated existing summary for {target_date}")
            
            return summary
            
    except Exception as e:
        logger.error(f"Error in recompute_daily_summary_for_date: {e}")
        DailySummary.objects.filter(date=target_date).delete()
        return None


def generate_daily_summaries_for_range(start_date, end_date):
    try:
        delta = end_date - start_date
        success_count = 0
        error_count = 0
        
        for i in range(delta.days + 1):
            current_date = start_date + timedelta(days=i)
            try:
                result = recompute_daily_summary_for_date(current_date)
                if result:
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(f"Error generating summary for {current_date}: {e}")
                error_count += 1
        
        logger.info(f"Generated {success_count} summaries, {error_count} errors")
        return success_count, error_count
        
    except Exception as e:
        logger.error(f"Error in generate_daily_summaries_for_range: {e}")
        return 0, 0


def get_daily_summary_stats(date):
    try:
        summary = DailySummary.objects.filter(date=date).first()
        
        if summary:
            return {
                'date': summary.date,
                'total_sales': summary.total_sales,
                'total_purchases': summary.total_purchases,
                'total_profit': summary.total_profit,
                'net_balance': summary.net_balance,
                'transactions_count': summary.transactions_count,
                'items_sold': summary.items_sold,
                'customers_count': summary.customers_count,
                'is_final': summary.is_final,
                'source': 'cached',
            }
        return compute_daily_stats(date)
    except Exception as e:
        logger.error(f"Error in get_daily_summary_stats: {e}")
        return None

def compute_daily_stats(date):
    try:
        transactions = DailySaleTransaction.objects.filter(date=date)
        
        if not transactions.exists():
            return None
        
        agg_data = transactions.aggregate(
            total_sales=Sum('total_amount', filter=Q(transaction_type='sale')),
            total_purchases=Sum('total_amount', filter=Q(transaction_type='purchase')),
            transactions_count=Count('id'),
            items_sold=Sum('quantity', filter=Q(transaction_type='sale')),
            customers_count=Count('customer', distinct=True, filter=Q(transaction_type='sale')),
        )
        total_sales = agg_data.get('total_sales') or Decimal('0.00')
        total_purchases = agg_data.get('total_purchases') or Decimal('0.00')
        total_profit = total_sales - total_purchases
        payments_total = Payment.objects.filter(
            date=date
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        
        net_balance = total_sales - payments_total
        
        return {
            'date': date,
            'total_sales': total_sales,
            'total_purchases': total_purchases,
            'total_profit': total_profit,
            'net_balance': net_balance,
            'transactions_count': agg_data.get('transactions_count') or 0,
            'items_sold': agg_data.get('items_sold') or 0,
            'customers_count': agg_data.get('customers_count') or 0,
            'is_final': False,
            'source': 'computed',
        }
        
    except Exception as e:
        logger.error(f"Error in compute_daily_stats: {e}")
        return None


def check_and_fix_daily_summaries():
    try:
        logger.info("Checking DailySummary table...")
        transaction_dates = DailySaleTransaction.objects.dates('date', 'day').distinct()
        summary_dates = DailySummary.objects.dates('date', 'day').distinct()       
        missing_dates = set(transaction_dates) - set(summary_dates)
        extra_dates = set(summary_dates) - set(transaction_dates)       
        logger.info(f"Found {len(missing_dates)} missing dates, {len(extra_dates)} extra dates")
        if extra_dates:
            DailySummary.objects.filter(date__in=list(extra_dates)).delete()
            logger.info(f"Removed {len(extra_dates)} extra summaries")
        success_count = 0
        for date in missing_dates:
            try:
                recompute_daily_summary_for_date(date)
                success_count += 1
            except Exception as e:
                logger.error(f"Error processing {date}: {e}")
        
        logger.info(f"Fixed {success_count} missing summaries")
        return success_count, len(missing_dates)
        
    except Exception as e:
        logger.error(f"Error in check_and_fix_daily_summaries: {e}")
        return 0, 0
def recompute_outstanding_for_customer(customer_id):
    if not customer_id:
        logger.warning("recompute_outstanding_for_customer called with no customer_id")
        return
    
    from .models import DailySaleTransaction, OutstandingCustomer, Payment
    
    logger.info(f"Recomputing outstanding for customer: {customer_id}")
    
    try:
        with db_transaction.atomic():
            transactions = DailySaleTransaction.objects.filter(customer_id=customer_id)
            if not transactions.exists():
                OutstandingCustomer.objects.filter(customer_id=customer_id).delete()
                logger.info(f"No transactions for customer {customer_id}")
                return
            
            total_debt = Decimal('0.00')
            tx_count = 0
            last_tx_date = None
            for tx in transactions:
                paid = Payment.objects.filter(transaction=tx).aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0.00')
                remaining = (tx.total_amount or Decimal('0.00')) - paid
                
                if remaining > Decimal('0.00'):
                    total_debt += remaining
                    tx_count += 1
                    if tx.date and (not last_tx_date or tx.date > last_tx_date):
                        last_tx_date = tx.date
            if total_debt > Decimal('0.00'):
                defaults = {
                    'total_debt': total_debt,
                    'transactions_count': tx_count,
                    'last_transaction': last_tx_date,
                    'updated_at': timezone.now(),
                }
                OutstandingCustomer.objects.update_or_create(
                    customer_id=customer_id,
                    defaults=defaults
                )
                logger.info(f"Outstanding updated for customer {customer_id}: {total_debt}")
            else:
                OutstandingCustomer.objects.filter(customer_id=customer_id).delete()
                logger.info(f"No debt for customer {customer_id}, record deleted")
                
    except Exception as e:
        logger.error(f"Error in recompute_outstanding_for_customer for customer {customer_id}: {str(e)}")
        if __name__ != '__main__':
            raise

def recompute_all_summaries(start_date=None, end_date=None):
    logger.info("Starting recompute of all daily summaries")
    qs = DailySaleTransaction.objects.all()   
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)
    dates = qs.values_list('date', flat=True).distinct()
    date_list = list(dates)
    
    logger.info(f"Found {len(date_list)} unique dates to process")    
    success_count = 0
    error_count = 0
    
    for d in date_list:
        try:
            recompute_daily_summary_for_date(d)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to recompute summary for {d}: {e}")
            error_count += 1
    
    logger.info(f"Recompute completed: {success_count} successful, {error_count} failed")
    return success_count, error_count

def get_customer_outstanding_summary(customer_id):
    try:
        outstanding = OutstandingCustomer.objects.filter(customer_id=customer_id).first()
        if outstanding:
            return {
                'total_debt': outstanding.total_debt,
                'transactions_count': outstanding.transactions_count,
                'last_transaction': outstanding.last_transaction,
                'updated_at': outstanding.updated_at,
            }
        return None
    except Exception as e:
        logger.error(f"Error getting customer outstanding summary: {e}")
        return None

def get_daily_summary_by_date(target_date):
    try:
        summary = DailySummary.objects.filter(date=target_date).first()
        if summary:
            return {
                'date': summary.date,
                'total_sales': summary.total_sales,
                'total_purchases': summary.total_purchases,
                'total_profit': summary.total_profit,
                'net_balance': summary.net_balance,
                'transactions_count': summary.transactions_count,
                'items_sold': summary.items_sold,
                'customers_count': summary.customers_count,
                'is_final': summary.is_final,
                'updated_at': summary.updated_at,
            }
        return None
    except Exception as e:
        logger.error(f"Error getting daily summary: {e}")
        return None