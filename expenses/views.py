from django.shortcuts import render
from datetime import datetime, timedelta
from .models import ExpenseRecord, DailyExpense
from .report import get_expense_summary, get_expenses_by_category, get_monthly_expenses

def expense_report(request):
    """گزارش هزینه‌ها"""
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if not start_date:
        start_date = datetime.now().date() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now().date()
    
    expenses = ExpenseRecord.objects.select_related('item', 'item__category').filter(
        date__range=[start_date, end_date]
    )
    
    daily_expenses = DailyExpense.objects.select_related('category').filter(
        date__range=[start_date, end_date]
    )
    
    summary = get_expense_summary(start_date, end_date)
    
    context = {
        'expenses': expenses,
        'daily_expenses': daily_expenses,
        'summary': summary,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'expenses/report.html', context)

def expense_dashboard(request):
    """داشبورد"""
    today = datetime.now().date()
    month_start = today.replace(day=1)
    
    summary = get_expense_summary(month_start, today)
    category_data = get_expenses_by_category(month_start, today)
    monthly_data = get_monthly_expenses(6)
    
    context = {
        'summary': summary,
        'category_data': category_data,
        'monthly_data': monthly_data,
    }
    return render(request, 'expense_dashboard.html', context)