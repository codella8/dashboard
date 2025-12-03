from django.db.models import Sum, Count, Avg, Q
from datetime import datetime, timedelta
from decimal import Decimal
from .models import ExpenseCategory, ExpenseRecord, DailyExpense

def get_expense_summary(start_date=None, end_date=None):
    """خلاصه هزینه‌ها"""
    expense_records = ExpenseRecord.objects.all()
    daily_expenses = DailyExpense.objects.all()
    
    if start_date:
        expense_records = expense_records.filter(date__gte=start_date)
        daily_expenses = daily_expenses.filter(date__gte=start_date)
    
    if end_date:
        expense_records = expense_records.filter(date__lte=end_date)
        daily_expenses = daily_expenses.filter(date__lte=end_date)
    
    # محاسبات هزینه‌های جزئی - جداگانه
    total_expense_amount = expense_records.aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0')
    
    total_expense_count = expense_records.count()
    
    # میانگین را جداگانه محاسبه کنیم
    avg_expense = total_expense_amount / total_expense_count if total_expense_count > 0 else Decimal('0')
    
    # محاسبات هزینه‌های روزانه
    daily_stats = daily_expenses.aggregate(
        total_amount=Sum('amount'),
        expense_count=Count('id')
    )
    
    # کل هزینه‌ها
    total_expenses = total_expense_amount + (daily_stats['total_amount'] or Decimal('0'))
    
    return {
        'expense_records': {
            'total_amount': total_expense_amount,
            'record_count': total_expense_count,
            'avg_expense': avg_expense
        },
        'daily_expenses': daily_stats,
        'total_expenses': total_expenses,
        'total_records': total_expense_count + (daily_stats['expense_count'] or 0)
    }

def get_expenses_by_category(start_date=None, end_date=None):
    """هزینه‌ها بر اساس دسته‌بندی"""
    # هزینه‌های جزئی
    expense_by_category = ExpenseRecord.objects.all()
    
    # هزینه‌های روزانه
    daily_by_category = DailyExpense.objects.all()
    
    if start_date:
        expense_by_category = expense_by_category.filter(date__gte=start_date)
        daily_by_category = daily_by_category.filter(date__gte=start_date)
    
    if end_date:
        expense_by_category = expense_by_category.filter(date__lte=end_date)
        daily_by_category = daily_by_category.filter(date__lte=end_date)
    
    # گروه‌بندی هزینه‌های جزئی
    expense_data = expense_by_category.values(
        'item__category__name'
    ).annotate(
        total_amount=Sum('total_amount'),
        record_count=Count('id')
    ).order_by('-total_amount')
    
    # گروه‌بندی هزینه‌های روزانه
    daily_data = daily_by_category.values(
        'category__name'
    ).annotate(
        total_amount=Sum('amount'),
        expense_count=Count('id')
    ).order_by('-total_amount')
    
    return {
        'expense_by_category': list(expense_data),
        'daily_by_category': list(daily_data)
    }

def get_monthly_expenses(months=6):
    """هزینه‌های ماهانه"""
    from django.utils import timezone
    from django.db.models.functions import ExtractMonth, ExtractYear
    
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=months*30)
    
    monthly_expenses = ExpenseRecord.objects.filter(
        date__range=[start_date, end_date]
    ).annotate(
        year=ExtractYear('date'),
        month=ExtractMonth('date')
    ).values('year', 'month').annotate(
        total_amount=Sum('total_amount'),
        count=Count('id')
    ).order_by('year', 'month')
    
    monthly_daily = DailyExpense.objects.filter(
        date__range=[start_date, end_date]
    ).annotate(
        year=ExtractYear('date'),
        month=ExtractMonth('date')
    ).values('year', 'month').annotate(
        total_amount=Sum('amount'),
        count=Count('id')
    ).order_by('year', 'month')
    
    return {
        'monthly_expenses': list(monthly_expenses),
        'monthly_daily': list(monthly_daily)
    }