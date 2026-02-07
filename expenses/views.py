# views.py
from django.shortcuts import render
from django.db.models import Sum, Count, Avg, Max, Min, F, ExpressionWrapper, DecimalField
from django.db.models.functions import TruncMonth, TruncWeek, TruncDay
from django.utils import timezone
from datetime import timedelta, datetime
from decimal import Decimal
from .models import Expense, ExpenseCategory
from django.contrib.auth.decorators import login_required


@login_required
def expenses_dashboard(request):
    # پارامترهای تاریخ از URL
    today = timezone.now().date()
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # تنظیم تاریخ‌های پیش‌فرض
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    else:
        start_date = today.replace(day=1)  # اول ماه جاری
    
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    else:
        end_date = today
    
    # فیلتر هزینه‌ها بر اساس تاریخ
    expenses = Expense.objects.filter(
        date__gte=start_date,
        date__lte=end_date
    )
    
    # محاسبه total_amount به صورت annotation
    expenses_with_total = expenses.annotate(
        total_amount_calc=ExpressionWrapper(
            F('quantity') * F('unit_price'),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )
    )
    
    # ۱. آمار کلی
    total_expenses = expenses_with_total.aggregate(
        total_amount=Sum('total_amount_calc'),
        count=Count('id'),
        avg_amount=Avg('total_amount_calc'),
        max_amount=Max('total_amount_calc'),
        min_amount=Min('total_amount_calc')
    )
    
    # ۲. آمار بر اساس دسته‌بندی
    category_stats = expenses_with_total.values(
        'category__name', 'category__id'
    ).annotate(
        total=Sum('total_amount_calc'),
        count=Count('id'),
        avg_amount=Avg('total_amount_calc'),
        avg_unit_price=Avg('unit_price'),
        total_quantity=Sum('quantity')
    ).order_by('-total')
    
    # ۳. آمار بر اساس روش پرداخت
    total_amount_value = total_expenses['total_amount'] or Decimal('0')
    payment_method_stats = expenses_with_total.values(
        'payment_method'
    ).annotate(
        total=Sum('total_amount_calc'),
        count=Count('id'),
        avg_amount=Avg('total_amount_calc')
    ).order_by('-total')
    
    # محاسبه درصد برای هر روش پرداخت
    payment_method_stats_list = []
    for stat in payment_method_stats:
        percentage = 0
        if total_amount_value > 0:
            percentage = (stat['total'] / total_amount_value) * 100
        payment_method_stats_list.append({
            'payment_method': stat['payment_method'],
            'payment_method_display': dict(Expense.PAYMENT_METHODS).get(stat['payment_method'], stat['payment_method']),
            'total': stat['total'],
            'count': stat['count'],
            'avg_amount': stat['avg_amount'],
            'percentage': round(percentage, 2)
        })
    
    # ۴. روند ماهانه (۶ ماه اخیر)
    six_months_ago = today - timedelta(days=180)
    monthly_trend = Expense.objects.filter(
        date__gte=six_months_ago
    ).annotate(
        month=TruncMonth('date'),
        total_amount_calc=ExpressionWrapper(
            F('quantity') * F('unit_price'),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )
    ).values('month').annotate(
        total=Sum('total_amount_calc'),
        count=Count('id'),
        avg_amount=Avg('total_amount_calc')
    ).order_by('month')
    
    # ۵. هزینه‌های روزانه (۳۰ روز اخیر)
    thirty_days_ago = today - timedelta(days=30)
    daily_expenses = Expense.objects.filter(
        date__gte=thirty_days_ago
    ).annotate(
        day=TruncDay('date'),
        total_amount_calc=ExpressionWrapper(
            F('quantity') * F('unit_price'),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )
    ).values('day').annotate(
        total=Sum('total_amount_calc'),
        count=Count('id')
    ).order_by('day')
    
    # ۶. ۱۰ هزینه اخیر با total_amount
    recent_expenses = expenses_with_total.select_related('category').order_by('-date', '-id')[:10]
    
    # ۷. توزیع مقدار واحد (unit_price)
    price_distribution = {
        'low': expenses.filter(unit_price__lt=100).count(),
        'medium': expenses.filter(unit_price__gte=100, unit_price__lt=1000).count(),
        'high': expenses.filter(unit_price__gte=1000).count(),
    }
    
    # ۸. آمار quantity
    quantity_stats = expenses.aggregate(
        total_quantity=Sum('quantity'),
        avg_quantity=Avg('quantity'),
        max_quantity=Max('quantity'),
        min_quantity=Min('quantity')
    )
    
    # ۹. top پرداخت‌های (paid_to)
    top_recipients = expenses_with_total.exclude(paid_to='').values(
        'paid_to'
    ).annotate(
        total=Sum('total_amount_calc'),
        count=Count('id'),
        avg_amount=Avg('total_amount_calc')
    ).order_by('-total')[:5]
    
    # ۱۰. میانگین هزینه بر اساس روزهای هفته
    weekly_avg = expenses_with_total.annotate(
        weekday=F('date__week_day')
    ).values('weekday').annotate(
        avg_amount=Avg('total_amount_calc'),
        total_amount=Sum('total_amount_calc'),
        count=Count('id')
    ).order_by('weekday')
    
    # روزهای هفته برای نمایش
    weekdays_map = {
        1: 'شنبه',
        2: 'یکشنبه',
        3: 'دوشنبه',
        4: 'سه‌شنبه',
        5: 'چهارشنبه',
        6: 'پنجشنبه',
        7: 'جمعه'
    }
    weekly_avg_list = []
    for item in weekly_avg:
        weekly_avg_list.append({
            'weekday': item['weekday'],
            'weekday_name': weekdays_map.get(item['weekday'], 'نامشخص'),
            'avg_amount': item['avg_amount'],
            'total_amount': item['total_amount'],
            'count': item['count']
        })
    
    # ۱۱. محاسبه تعداد روزها و میانگین روزانه
    days_count = (end_date - start_date).days + 1
    avg_daily_expense = Decimal('0')
    if days_count > 0 and total_amount_value:
        avg_daily_expense = total_amount_value / days_count
    
    # ۱۲. آمار ۱۰ هزینه برتر (بیشترین مبلغ)
    top_expenses = expenses_with_total.select_related('category').order_by('-total_amount_calc')[:10]
    
    # ۱۳. آمار unit_price
    unit_price_stats = expenses.aggregate(
        avg_unit_price=Avg('unit_price'),
        max_unit_price=Max('unit_price'),
        min_unit_price=Min('unit_price')
    )
    
    context = {
        # اطلاعات تاریخ
        'start_date': start_date,
        'end_date': end_date,
        'today': today,
        
        # آمار کلی
        'total_amount': total_amount_value,
        'total_count': total_expenses['count'] or 0,
        'avg_amount': total_expenses['avg_amount'] or Decimal('0'),
        'max_amount': total_expenses['max_amount'] or Decimal('0'),
        'min_amount': total_expenses['min_amount'] or Decimal('0'),
        
        # داده‌های تفکیکی
        'category_stats': list(category_stats),
        'payment_method_stats': payment_method_stats_list,
        'monthly_trend': list(monthly_trend),
        'daily_expenses': list(daily_expenses),
        'recent_expenses': recent_expenses,
        'top_expenses': top_expenses,
        'price_distribution': price_distribution,
        'quantity_stats': quantity_stats,
        'unit_price_stats': unit_price_stats,
        'top_recipients': list(top_recipients),
        'weekly_avg': weekly_avg_list,
        
        # برای نمایش در تمپلیت
        'categories': ExpenseCategory.objects.filter(is_active=True),
        'payment_methods': dict(Expense.PAYMENT_METHODS),
        
        # محاسبات اضافی
        'days_count': days_count,
        'avg_daily_expense': round(avg_daily_expense, 2),
        
        # فرمت تاریخ برای JavaScript
        'start_date_js': start_date.strftime('%Y-%m-%d'),
        'end_date_js': end_date.strftime('%Y-%m-%d'),
    }
    
    return render(request, "expenses/expenses_dashboard.html", context)


@login_required
def category_detail(request, category_id):
    category = ExpenseCategory.objects.get(id=category_id)
    
    # پارامترهای تاریخ از URL
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    expenses = Expense.objects.filter(category=category)
    
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        expenses = expenses.filter(date__gte=start_date)
    
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        expenses = expenses.filter(date__lte=end_date)
    
    # اضافه کردن total_amount به صورت annotation
    expenses_with_total = expenses.annotate(
        total_amount_calc=ExpressionWrapper(
            F('quantity') * F('unit_price'),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )
    )
    
    # آمار دسته‌بندی
    stats = expenses_with_total.aggregate(
        total=Sum('total_amount_calc'),
        count=Count('id'),
        avg_amount=Avg('total_amount_calc'),
        avg_quantity=Avg('quantity'),
        avg_unit_price=Avg('unit_price'),
        max_amount=Max('total_amount_calc'),
        min_amount=Min('total_amount_calc')
    )
    
    # آمار ماهانه برای این دسته‌بندی
    monthly_stats = expenses_with_total.annotate(
        month=TruncMonth('date')
    ).values('month').annotate(
        total=Sum('total_amount_calc'),
        count=Count('id')
    ).order_by('-month')[:12]
    
    context = {
        'category': category,
        'expenses': expenses_with_total.select_related('category').order_by('-date')[:50],  # 50 مورد آخر
        'stats': stats,
        'monthly_stats': list(monthly_stats),
        'payment_methods': dict(Expense.PAYMENT_METHODS),
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return render(request, "expenses/category_detail.html", context)


@login_required
def monthly_report(request, year=None, month=None):
    today = timezone.now().date()
    if year and month:
        report_date = datetime(year, month, 1).date()
    else:
        report_date = today.replace(day=1)
    
    next_month = report_date.replace(day=28) + timedelta(days=4)
    month_end = next_month - timedelta(days=next_month.day)
    
    expenses = Expense.objects.filter(
        date__gte=report_date,
        date__lte=month_end
    ).annotate(
        total_amount_calc=ExpressionWrapper(
            F('quantity') * F('unit_price'),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )
    )
    
    # آمار ماهانه
    monthly_stats = expenses.aggregate(
        total=Sum('total_amount_calc'),
        count=Count('id'),
        avg_daily=Sum('total_amount_calc') / month_end.day,
        avg_per_expense=Avg('total_amount_calc')
    )
    
    # آمار روزانه
    daily_stats = expenses.annotate(
        day=TruncDay('date')
    ).values('day').annotate(
        total=Sum('total_amount_calc'),
        count=Count('id'),
        avg_amount=Avg('total_amount_calc')
    ).order_by('day')
    
    # آمار بر اساس دسته‌بندی
    category_stats = expenses.values(
        'category__name', 'category__id'
    ).annotate(
        total=Sum('total_amount_calc'),
        count=Count('id')
    ).order_by('-total')
    
    # آمار بر اساس روش پرداخت
    payment_stats = expenses.values(
        'payment_method'
    ).annotate(
        total=Sum('total_amount_calc'),
        count=Count('id')
    ).order_by('-total')
    
    context = {
        'report_date': report_date,
        'month_end': month_end,
        'monthly_stats': monthly_stats,
        'daily_stats': daily_stats,
        'category_stats': list(category_stats),
        'payment_stats': list(payment_stats),
        'expenses': expenses.select_related('category').order_by('-date'),
        'categories': ExpenseCategory.objects.filter(is_active=True),
    }
    
    return render(request, "expenses/monthly_report.html", context)