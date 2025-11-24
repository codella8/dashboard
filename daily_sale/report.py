from decimal import Decimal
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import Coalesce, TruncDay, TruncMonth
from .models import DailySaleTransaction, DailySummary
from django.utils import timezone
from datetime import date, timedelta
from django.db import transaction

def auto_update_daily_summary(target_date=None):
    """به‌روزرسانی خودکار تمام خلاصه‌های روزانه"""
    if not target_date:
        target_date = timezone.now().date()
    
    try:
        with transaction.atomic():
            summary, created = DailySummary.objects.get_or_create(date=target_date)
            summary.save()  # این باعث محاسبه خودکار می‌شود
            
            # به‌روزرسانی خلاصه ۷ روز گذشته (برای نمودارها)
            for i in range(1, 8):
                past_date = target_date - timedelta(days=i)
                past_summary, _ = DailySummary.objects.get_or_create(date=past_date)
                past_summary.save()
                
        return summary
    except Exception as e:
        print(f"خطا در به‌روزرسانی خلاصه: {e}")
        return None

def get_dashboard_data(days=30):
    """داده‌های هوشمند برای داشبورد"""
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)
    
    # به‌روزرسانی خودکار خلاصه‌ها
    auto_update_daily_summary(end_date)
    
    # داده‌های خلاصه
    summaries = DailySummary.objects.filter(
        date__range=[start_date, end_date]
    ).order_by('date')
    
    # آمار کلی
    total_stats = summaries.aggregate(
        total_sales = Coalesce(Sum('total_sales'), Decimal('0.00')),
        total_profit = Coalesce(Sum('total_profit'), Decimal('0.00')),
    )

    
    # پرفروش‌ترین روزها
    top_days = summaries.order_by('-total_sales')[:5]
    
    # روند فروش
    sales_trend = list(summaries.values('date', 'total_sales', 'transactions_count'))
    
    return {
        'period': {'start': start_date, 'end': end_date, 'days': days},
        'totals': total_stats,
        'top_days': top_days,
        'trend': sales_trend,
        'currency_breakdown': get_currency_breakdown(start_date, end_date),
        'performance_metrics': get_performance_metrics(start_date, end_date)
    }

def get_currency_breakdown(start_date, end_date):
    """تجزیه هوشمند ارزها"""
    transactions = DailySaleTransaction.objects.filter(
        date__range=[start_date, end_date]
    )
    
    return transactions.values('currency').annotate(
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
        transaction_count=Coalesce(Count('id'), 0),
    ).order_by('-total_amount')

def get_performance_metrics(start_date, end_date):
    """معیارهای عملکرد هوشمند"""
    transactions = DailySaleTransaction.objects.filter(
        date__range=[start_date, end_date],
        transaction_type='sale'
    )
    
    metrics = transactions.aggregate(
        total_revenue=Coalesce(Sum('total_amount'), Decimal('0.00')),
        total_items=Coalesce(Sum('quantity'), 0),
        success_rate=Coalesce(
            Count('id', filter=Q(status='paid')) * 100.0 / Count('id'), 
            0.0
        )
    )
    
    # محاسبه نرخ رشد
    previous_period_end = start_date - timedelta(days=1)
    previous_period_start = previous_period_end - (end_date - start_date)
    
    previous_revenue = DailySaleTransaction.objects.filter(
        date__range=[previous_period_start, previous_period_end],
        transaction_type='sale'
    ).aggregate(
        total=Coalesce(Sum('total_amount'), Decimal('0.00'))
    )['total']
    
    current_revenue = metrics['total_revenue']
    
    if previous_revenue > 0:
        growth_rate = ((current_revenue - previous_revenue) / previous_revenue * 100).quantize(Decimal('0.01'))
    else:
        growth_rate = Decimal('100.00') if current_revenue > 0 else Decimal('0.00')
    
    metrics['growth_rate'] = growth_rate
    return metrics

def get_auto_alerts():
    """هشدارهای خودکار سیستم"""
    alerts = []
    today = timezone.now().date()
    
    # بررسی تراکنش‌های معلق
    pending_transactions = DailySaleTransaction.objects.filter(
        status='pending',
        date__lt=today - timedelta(days=3)
    ).count()
    
    if pending_transactions > 0:
        alerts.append({
            'type': 'warning',
            'message': f'{pending_transactions} تراکنش قدیمی در وضعیت معلق',
            'action': 'review_pending'
        })
    
    # بررسی موجودی کم
    from containers.models import Inventory_List
    low_stock = Inventory_List.objects.filter(
        in_stock_qty__lt=10
    ).count()
    
    if low_stock > 0:
        alerts.append({
            'type': 'danger',
            'message': f'{low_stock} کالا در آستانه اتمام موجودی',
            'action': 'check_inventory'
        })
    
    # بررسی خلاصه‌های به‌روزنشده
    missing_summaries = DailySummary.objects.filter(
        date__lt=today - timedelta(days=1),
        is_final=False
    ).count()
    
    if missing_summaries > 0:
        alerts.append({
            'type': 'info',
            'message': f'{missing_summaries} خلاصه روزانه نیاز به بررسی',
            'action': 'update_summaries'
        })
    
    return alerts

# جایگزینی توابع قدیمی با نسخه‌های هوشمند
update_daily_summary = auto_update_daily_summary
get_daily_summary = lambda date: DailySummary.objects.get_or_create(date=date)[0]
get_dashboard_data = get_dashboard_data
get_alerts = get_auto_alerts