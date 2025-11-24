from decimal import Decimal
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction as db_transaction
from django.db.models import Sum, Count, Avg, Q
from django.db.models.functions import Coalesce, TruncDay, TruncMonth
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.contrib import messages

from .models import DailySaleTransaction, DailySummary
from .forms import DailySaleTransactionForm
from .report import (
    auto_update_daily_summary,
    get_dashboard_data,
    get_auto_alerts,
    get_currency_breakdown,
    get_performance_metrics
)

def parse_date(date_string, default=None):
    """تبدیل هوشمند رشته به تاریخ"""
    if not date_string:
        return default
    
    try:
        return datetime.strptime(date_string, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return default

def get_date_range(days=30):
    """محاسبه خودکار بازه تاریخ"""
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)
    return start_date, end_date

def format_currency(amount, currency='usd'):
    """فرمت‌دهی هوشمند ارز"""
    currency_symbols = {
        'usd': '$',
        'eur': '€',
        'aed': 'AED '
    }
    symbol = currency_symbols.get(currency, '')
    return f"{symbol}{amount:,.0f}"


@login_required
def transaction_list(request):
    """لیست هوشمند تراکنش‌ها با فیلترهای پیشرفته"""
    search_query = request.GET.get('q', '')
    transaction_type = request.GET.get('type', '')
    status_filter = request.GET.get('status', '')
    customer_id = request.GET.get('customer', '')
    currency_filter = request.GET.get('currency', '')
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))
    
    # کوئری پایه
    transactions = DailySaleTransaction.objects.all().select_related(
        'item', 'customer', 'container', 'company'
    ).order_by('-date', '-created_at')
    
    # فیلترهای هوشمند
    if search_query:
        transactions = transactions.filter(
            Q(invoice_number__icontains=search_query) |
            Q(item__product_name__icontains=search_query) |
            Q(customer__first_name__icontains=search_query) |
            Q(customer__last_name__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    if status_filter:
        transactions = transactions.filter(status=status_filter)
    
    if customer_id:
        transactions = transactions.filter(customer_id=customer_id)
    
    if currency_filter:
        transactions = transactions.filter(currency=currency_filter)
    
    if start_date and end_date:
        transactions = transactions.filter(date__range=[start_date, end_date])
    elif start_date:
        transactions = transactions.filter(date__gte=start_date)
    elif end_date:
        transactions = transactions.filter(date__lte=end_date)
    
    # آمار سریع
    quick_stats = transactions.aggregate(
        total_count=Count('id'),
        total_amount=Coalesce(Sum('total_amount'), Decimal('0.00')),
        avg_amount=Coalesce(Avg('total_amount'), Decimal('0.00')),
        pending_count=Count('id', filter=Q(status='pending'))
    )
    
    # صفحه‌بندی هوشمند
    page_size = int(request.GET.get('page_size', 25))
    paginator = Paginator(transactions, page_size)
    page_number = request.GET.get('page', 1)
    
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    context = {
        'transactions': page_obj,
        'quick_stats': quick_stats,
        'filters': {
            'q': search_query,
            'type': transaction_type,
            'status': status_filter,
            'customer': customer_id,
            'currency': currency_filter,
            'start_date': request.GET.get('start_date', ''),
            'end_date': request.GET.get('end_date', ''),
            'page_size': page_size,
        },
        'alerts': get_auto_alerts(),
    }
    
    return render(request, 'daily_sale/transaction_list.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def create_transaction(request):
    """ایجاد هوشمند تراکنش جدید"""
    if request.method == 'POST':
        form = DailySaleTransactionForm(request.POST)
        if form.is_valid():
            try:
                with db_transaction.atomic():
                    transaction = form.save(commit=False)
                    transaction.created_by = request.user
                    
                    # تمام محاسبات به صورت خودکار در save انجام می‌شود
                    transaction.save()
                    
                    # به‌روزرسانی خودکار خلاصه روزانه
                    auto_update_daily_summary(transaction.date)
                    
                messages.success(request, f'تراکنش {transaction.invoice_number} با موفقیت ایجاد شد.')
                return redirect('daily_sale:transaction_list')
                
            except Exception as e:
                messages.error(request, f'خطا در ایجاد تراکنش: {str(e)}')
    else:
        # مقداردهی اولیه هوشمند
        initial_data = {
            'date': timezone.now().date(),
            'status': 'pending',
            'currency': 'usd',
            'quantity': 1,
        }
        form = DailySaleTransactionForm(initial=initial_data)
    
    return render(request, 'daily_sale/transaction_form.html', {
        'form': form,
        'title': 'ایجاد تراکنش جدید',
        'action_url': 'daily_sale:create_transaction'
    })

@login_required
@require_http_methods(["GET", "POST"])
def edit_transaction(request, transaction_id):
    """ویرایش هوشمند تراکنش"""
    transaction_obj = get_object_or_404(DailySaleTransaction, id=transaction_id)
    
    if request.method == 'POST':
        form = DailySaleTransactionForm(request.POST, instance=transaction_obj)
        if form.is_valid():
            try:
                with db_transaction.atomic():
                    old_date = transaction_obj.date
                    transaction = form.save()
                    
                    # به‌روزرسانی خلاصه روزانه برای تاریخ قدیم و جدید
                    if old_date != transaction.date:
                        auto_update_daily_summary(old_date)
                    auto_update_daily_summary(transaction.date)
                    
                messages.success(request, f'تراکنش {transaction.invoice_number} با موفقیت ویرایش شد.')
                return redirect('daily_sale:transaction_list')
                
            except Exception as e:
                messages.error(request, f'خطا در ویرایش تراکنش: {str(e)}')
    else:
        form = DailySaleTransactionForm(instance=transaction_obj)
    
    return render(request, 'daily_sale/transaction_form.html', {
        'form': form,
        'transaction': transaction_obj,
        'title': 'ویرایش تراکنش',
        'action_url': 'daily_sale:edit_transaction'
    })

@login_required
@require_http_methods(["GET", "POST"])
def delete_transaction(request, transaction_id):
    """حذف هوشمند تراکنش"""
    transaction_obj = get_object_or_404(DailySaleTransaction, id=transaction_id)
    
    if request.method == 'POST':
        try:
            with db_transaction.atomic():
                transaction_date = transaction_obj.date
                invoice_number = transaction_obj.invoice_number
                transaction_obj.delete()
                
                # به‌روزرسانی خودکار خلاصه روزانه
                auto_update_daily_summary(transaction_date)
                
            messages.success(request, f'تراکنش {invoice_number} با موفقیت حذف شد.')
            return redirect('daily_sale:transaction_list')
            
        except Exception as e:
            messages.error(request, f'خطا در حذف تراکنش: {str(e)}')
    
    return render(request, 'daily_sale/transaction_confirm_delete.html', {
        'transaction': transaction_obj
    })

@login_required
@require_http_methods(["POST"])
def bulk_action(request):
    """اقدامات گروهی هوشمند"""
    action = request.POST.get('action')
    transaction_ids = request.POST.getlist('transaction_ids')
    
    if not transaction_ids:
        messages.warning(request, 'هیچ تراکنشی انتخاب نشده است.')
        return redirect('daily_sale:transaction_list')
    
    transactions = DailySaleTransaction.objects.filter(id__in=transaction_ids)
    
    try:
        with db_transaction.atomic():
            if action == 'mark_paid':
                for transaction in transactions:
                    transaction.mark_as_paid()
                messages.success(request, f'{len(transactions)} تراکنش پرداخت شده علامت‌گذاری شد.')
                
            elif action == 'recalculate':
                for transaction in transactions:
                    transaction.calculate_financials()
                    transaction.save()
                messages.success(request, f'مقادیر مالی {len(transactions)} تراکنش بازمحاسبه شد.')
                
            elif action == 'delete':
                count = transactions.count()
                transactions.delete()
                messages.success(request, f'{count} تراکنش حذف شد.')
                
    except Exception as e:
        messages.error(request, f'خطا در انجام اقدام گروهی: {str(e)}')
    
    return redirect('daily_sale:transaction_list')


@login_required
def dashboard(request):
    """داشبورد هوشمند با تحلیل‌های پیشرفته"""
    # پارامترهای تاریخ
    days = int(request.GET.get('days', 30))
    start_date, end_date = get_date_range(days)
    
    # به‌روزرسانی خودکار داده‌ها
    auto_update_daily_summary()
    
    # دریافت داده‌های هوشمند
    dashboard_data = get_dashboard_data(days)
    
    # هشدارهای سیستم
    system_alerts = get_auto_alerts()
    
    # تراکنش‌های اخیر
    recent_transactions = DailySaleTransaction.objects.select_related(
        'item', 'customer'
    ).order_by('-created_at')[:10]
    
    # خلاصه امروز
    today_summary = DailySummary.objects.filter(date=timezone.now().date()).first()
    
    context = {
        **dashboard_data,
        'alerts': system_alerts,
        'recent_transactions': recent_transactions,
        'today_summary': today_summary,
        'selected_days': days,
    }
    
    return render(request, 'daily_sale/dashboard.html', context)

@login_required
def financial_reports(request):
    """گزارش‌های مالی هوشمند"""
    report_type = request.GET.get('type', 'daily')
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))
    
    if not start_date or not end_date:
        start_date, end_date = get_date_range(30)
    
    # به‌روزرسانی خلاصه‌ها
    auto_update_daily_summary()
    
    if report_type == 'daily':
        data = DailySummary.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('date')
        
    elif report_type == 'monthly':
        data = DailySummary.objects.filter(
            date__range=[start_date, end_date]
        ).annotate(
            month=TruncMonth('date')
        ).values('month').annotate(
            total_sales=Sum('total_sales'),
            total_profit=Sum('total_profit'),
            transaction_count=Sum('transactions_count')
        ).order_by('month')
        
    elif report_type == 'currency':
        data = get_currency_breakdown(start_date, end_date)
        
    else:
        data = []
    
    context = {
        'report_type': report_type,
        'start_date': start_date,
        'end_date': end_date,
        'data': data,
        'performance_metrics': get_performance_metrics(start_date, end_date),
    }
    
    return render(request, 'daily_sale/financial_reports.html', context)

@login_required
def sales_analytics(request):
    """تحلیل‌های پیشرفته فروش"""
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))
    
    if not start_date or not end_date:
        start_date, end_date = get_date_range(90)
    
    # تحلیل محصولات
    product_analysis = DailySaleTransaction.objects.filter(
        date__range=[start_date, end_date],
        transaction_type='sale'
    ).values('item__product_name').annotate(
        total_sales=Coalesce(Sum('total_amount'), Decimal('0.00')),
        total_quantity=Coalesce(Sum('quantity'), 0),
        avg_price=Coalesce(Avg('unit_price'), Decimal('0.00')),
        transaction_count=Count('id')
    ).order_by('-total_sales')[:20]
    
    # تحلیل مشتریان
    customer_analysis = DailySaleTransaction.objects.filter(
        date__range=[start_date, end_date],
        transaction_type='sale'
    ).values('customer__first_name', 'customer__last_name').annotate(
        total_purchases=Coalesce(Sum('total_amount'), Decimal('0.00')),
        purchase_count=Count('id'),
        avg_purchase=Coalesce(Avg('total_amount'), Decimal('0.00'))
    ).order_by('-total_purchases')[:15]
    
    # روند زمانی
    time_series = DailySummary.objects.filter(
        date__range=[start_date, end_date]
    ).values('date').annotate(
        daily_sales=Coalesce(Sum('total_sales'), Decimal('0.00')),
        daily_profit=Coalesce(Sum('total_profit'), Decimal('0.00'))
    ).order_by('date')
    
    context = {
        'start_date': start_date,
        'end_date': end_date,
        'product_analysis': product_analysis,
        'customer_analysis': customer_analysis,
        'time_series': list(time_series),
    }
    
    return render(request, 'daily_sale/sales_analytics.html', context)

@login_required
def inventory_reports(request):
    """گزارش‌های هوشمند موجودی"""
    from containers.models import Inventory_List
    
    # کالاهای با موجودی کم
    low_stock = Inventory_List.objects.filter(
        in_stock_qty__lt=10
    ).order_by('in_stock_qty')[:20]
    
    # پرفروش‌ترین کالاها
    top_sellers = Inventory_List.objects.filter(
        total_sold_qty__gt=0
    ).order_by('-total_sold_qty')[:15]
    
    # کالاهای بدون فروش
    no_sales = Inventory_List.objects.filter(
        total_sold_qty=0
    ).order_by('-in_stock_qty')[:10]
    
    context = {
        'low_stock': low_stock,
        'top_sellers': top_sellers,
        'no_sales': no_sales,
        'total_products': Inventory_List.objects.count(),
        'total_low_stock': low_stock.count(),
    }
    
    return render(request, 'daily_sale/inventory_reports.html', context)

# =============================================
# API VIEWS FOR AJAX
# =============================================

def get_dashboard_data(days=7):
    # محاسبه بازه زمانی
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days - 1)

    summaries = DailySummary.objects.filter(date__range=(start_date, end_date))

    # محاسبه آمار کلی
    total_stats = summaries.aggregate(
        total_sales = Coalesce(Sum('total_sales'), Decimal('0.00')),
        total_profit = Coalesce(Sum('total_profit'), Decimal('0.00')),
    )

    # استخراج مقدارها
    total_sales = total_stats['total_sales']
    total_profit = total_stats['total_profit']

    # سایر داده‌ها می‌توانید اضافه کنید …
    return {
        'total_sales': total_sales,
        'total_profit': total_profit,
        'days': days,
        'start_date': start_date,
        'end_date': end_date,
    }

@login_required
def api_dashboard_stats(request):
    """API برای آمار لحظه‌ای داشبورد"""
    # خواندن پارامتر days از درخواست، با پیش‌فرض 7
    try:
        days = int(request.GET.get('days', 7))
    except ValueError:
        days = 7

    data = get_dashboard_data(days)

    return JsonResponse({
        'success': True,
        'data': data
    })

@login_required
def api_quick_summary(request):
    """API برای خلاصه سریع"""
    date_param = request.GET.get('date')
    target_date = parse_date(date_param, timezone.now().date())
    
    summary = DailySummary.objects.filter(date=target_date).first()
    
    if not summary:
        summary = auto_update_daily_summary(target_date)
    
    return JsonResponse({
        'success': True,
        'date': target_date.isoformat(),
        'total_sales': float(summary.total_sales) if summary else 0,
        'total_profit': float(summary.total_profit) if summary else 0,
        'transactions_count': summary.transactions_count if summary else 0,
    })

@login_required
def api_recent_activity(request):
    """API برای فعالیت‌های اخیر"""
    limit = int(request.GET.get('limit', 10))
    
    activities = DailySaleTransaction.objects.select_related(
        'item', 'customer'
    ).order_by('-created_at')[:limit]
    
    activity_data = []
    for activity in activities:
        activity_data.append({
            'id': str(activity.id),
            'invoice_number': activity.invoice_number,
            'type': activity.get_transaction_type_display(),
            'customer': activity.customer.full_name if activity.customer else 'نامشخص',
            'amount': float(activity.total_amount),
            'currency': activity.currency,
            'status': activity.get_status_display(),
            'created_at': activity.created_at.isoformat(),
        })
    
    return JsonResponse({
        'success': True,
        'activities': activity_data
    })

@login_required
def api_system_alerts(request):
    """API برای هشدارهای سیستم"""
    alerts = get_auto_alerts()
    
    return JsonResponse({
        'success': True,
        'alerts': alerts,
        'count': len(alerts)
    })

# =============================================
# ADMIN VIEWS
# =============================================

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_control_panel(request):
    """پنل کنترل مدیریت"""
    # آمار سیستم
    system_stats = {
        'total_transactions': DailySaleTransaction.objects.count(),
        'total_customers': DailySaleTransaction.objects.values('customer').distinct().count(),
        'total_products': DailySaleTransaction.objects.values('item').distinct().count(),
        'pending_transactions': DailySaleTransaction.objects.filter(status='pending').count(),
    }
    
    # خلاصه‌های نیازمند توجه
    attention_summaries = DailySummary.objects.filter(
        is_final=False,
        date__lt=timezone.now().date() - timedelta(days=1)
    ).order_by('date')[:10]
    
    # اقدامات سیستم
    system_actions = [
        {
            'name': 'بازمحاسبه خلاصه امروز',
            'url': '#',
            'description': 'بازمحاسبه تمام آمار امروز'
        },
        {
            'name': 'بررسی تراکنش‌های معلق',
            'url': 'daily_sale:transaction_list?status=pending',
            'description': 'مدیریت تراکنش‌های در انتظار'
        },
        {
            'name': 'گزارش مالی هفتگی',
            'url': 'daily_sale:financial_reports?type=daily&days=7',
            'description': 'گزارش کامل هفته جاری'
        },
    ]
    
    context = {
        'system_stats': system_stats,
        'attention_summaries': attention_summaries,
        'system_actions': system_actions,
        'alerts': get_auto_alerts(),
    }
    
    return render(request, 'daily_sale/admin_control_panel.html', context)

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_bulk_operations(request):
    """عملیات گروهی مدیریت"""
    if request.method == 'POST':
        operation = request.POST.get('operation')
        
        try:
            with db_transaction.atomic():
                if operation == 'recalculate_all_summaries':
                    # بازمحاسبه تمام خلاصه‌ها
                    summaries = DailySummary.objects.filter(is_final=False)
                    for summary in summaries:
                        summary.calculate_totals()
                        summary.save()
                    
                    messages.success(request, f'تمام خلاصه‌ها بازمحاسبه شدند.')
                    
                elif operation == 'generate_missing_summaries':
                    # تولید خلاصه‌های گمشده
                    start_date = parse_date(request.POST.get('start_date'))
                    end_date = parse_date(request.POST.get('end_date'))
                    
                    if start_date and end_date:
                        current_date = start_date
                        created_count = 0
                        
                        while current_date <= end_date:
                            summary, created = DailySummary.objects.get_or_create(date=current_date)
                            if created:
                                summary.save()
                                created_count += 1
                            current_date += timedelta(days=1)
                        
                        messages.success(request, f'{created_count} خلاصه جدید ایجاد شد.')
                
        except Exception as e:
            messages.error(request, f'خطا در انجام عملیات: {str(e)}')
    
    return render(request, 'daily_sale/admin_bulk_operations.html')