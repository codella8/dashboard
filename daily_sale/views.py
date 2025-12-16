# daily_sale/views.py
from decimal import Decimal
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.contrib import messages
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.utils import timezone
from decimal import Decimal,ROUND_HALF_UP
from django.db.models import Sum, Q, F, Count
from django.db import connection
import json
from datetime import datetime, timedelta
from django.db.models.functions import Coalesce
from django.db.models import DecimalField
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from .models import DailySaleTransaction, Payment, OutstandingCustomer, DailySummary
from .forms import DailySaleTransactionForm, PaymentForm
from .report import get_sales_summary, sales_timeseries, outstanding_list, parse_date_param
# safe populate only submitted ids for performance:
from accounts.models import Company, UserProfile
from containers.models import Container, Inventory_List
from .utils import recompute_daily_summary_for_date, recompute_outstanding_for_customer,get_customer_outstanding_summary

logger = logging.getLogger(__name__)

TAX_RATE = Decimal('0.10')  # مالیات ۱۰٪

@login_required
def customer_detail(request, customer_id=None):
    
    if customer_id:
        if not request.user.is_staff:
            messages.error(request, "you do not have access to this page!")
            return redirect('accounts:home')
        
        # دریافت پروفایل مشتری مورد نظر
        customer = get_object_or_404(UserProfile, id=customer_id, role=UserProfile.ROLE_CUSTOMER)
        is_self_view = False
    
    else:
        # حالت ۲: کاربر عادی است و می‌خواهد پروفایل خودش را ببیند
        if request.user.is_staff:
            messages.info(request, "check from admin dashboard!")
            return redirect('accounts:dashboard')
        
        # پیدا کردن پروفایل کاربر فعلی
        try:
            customer = UserProfile.objects.get(user=request.user, role=UserProfile.ROLE_CUSTOMER)
            is_self_view = True
        except UserProfile.DoesNotExist:
            messages.error(request, "پروفایل مشتری برای شما یافت نشد.")
            return redirect('accounts:home')
    
    # محاسبه مجدد مانده بدهی (در صورت لزوم)
    recompute_outstanding_for_customer(customer.id)

    # دریافت خلاصه بدهی مشتری
    outstanding = get_customer_outstanding_summary(customer.id)
    total_debt = outstanding['total_debt'] if outstanding else Decimal('0.00')
    transactions_count = outstanding['transactions_count'] if outstanding else 0
    last_transaction = outstanding['last_transaction'] if outstanding else None

    # دریافت تراکنش‌های مشتری به ترتیب تاریخ
    transactions = DailySaleTransaction.objects.filter(customer=customer).select_related('item').order_by('-date')

    tx_data = []
    for tx in transactions:
        paid_amount = Payment.objects.filter(transaction=tx).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        remaining_amount = (tx.total_amount or Decimal('0.00')) - paid_amount

        # محاسبه مالیات دقیق به صورت درصدی
        tax_amount = (tx.total_amount or Decimal('0.00')) * TAX_RATE
        total_with_tax = (tx.total_amount or Decimal('0.00')) + tax_amount

        tx_data.append({
            'id': tx.id,
            'date': tx.date,
            'type': tx.get_transaction_type_display() if hasattr(tx, 'get_transaction_type_display') else tx.transaction_type,
            'item': tx.item.name if tx.item else '-',
            'quantity': tx.quantity,
            'unit_price': tx.item.unit_price if tx.item else Decimal('0.00'),
            'total_amount': tx.total_amount,
            'tax_amount': tax_amount,
            'total_with_tax': total_with_tax,
            'paid_amount': paid_amount,
            'remaining_amount': remaining_amount,
            'note': tx.note,
        })

    # جمع کل فروش و مالیات
    total_sales = sum((tx['total_amount'] or Decimal('0.00')) for tx in tx_data)
    total_tax = sum(tx['tax_amount'] for tx in tx_data)
    total_paid = sum(tx['paid_amount'] for tx in tx_data)
    total_remaining = sum(tx['remaining_amount'] for tx in tx_data)

    context = {
        'customer': customer,
        'transactions': tx_data,
        'total_sales': total_sales,
        'total_tax': total_tax,
        'total_paid': total_paid,
        'total_remaining': total_remaining,
        'transactions_count': transactions_count,
        'last_transaction': last_transaction,
        'tax_rate': TAX_RATE * 100,  # نمایش درصدی
        'is_self_view': is_self_view,  # آیا کاربر خودش را می‌بیند؟
        'is_admin': request.user.is_staff,  # آیا کاربر ادمین است؟
    }
    return render(request, 'daily_sale/customer_detail.html', context)

@login_required
def transaction_create(request):
    if request.method == "POST":
        form = DailySaleTransactionForm(request.POST)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.created_by = request.user
            
            # محاسبات اضافی در ویو (اختیاری - برای تأیید)
            # این محاسبات در مدل و فرم هم انجام شده است
            transaction.save()

            messages.success(request, "Transaction created successfully")
            return redirect("daily_sale:transaction_list")
    else:
        form = DailySaleTransactionForm(initial={
            "date": timezone.now().date(),
            "tax": 5,  # 5% پیش‌فرض
            "quantity": 1,
        })

    return render(request, "daily_sale/transaction_create.html", {"form": form})


# API endpoint برای محاسبه مالیات در زمان واقعی
@login_required
@require_GET
def calculate_tax_preview(request):
    """API endpoint for real-time tax calculation preview"""
    try:
        # دریافت پارامترها
        quantity = Decimal(request.GET.get('quantity', 1))
        unit_price = Decimal(request.GET.get('unit_price', 0))
        discount = Decimal(request.GET.get('discount', 0))
        tax_percent = Decimal(request.GET.get('tax', 5))
        advance = Decimal(request.GET.get('advance', 0))
        
        # محاسبه دقیق مثل ماشین حساب
        # 1. Subtotal
        subtotal = (quantity * unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        # 2. Taxable amount (after discount)
        taxable_amount = (subtotal - discount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if taxable_amount < Decimal('0'):
            taxable_amount = Decimal('0')
        
        # 3. Tax amount (percentage of taxable amount)
        tax_amount = (taxable_amount * (tax_percent / Decimal('100'))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        
        # 4. Total amount
        total_amount = (taxable_amount + tax_amount).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        
        # 5. Balance
        balance = (total_amount - advance).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        
        # وضعیت پرداخت
        if advance >= total_amount and total_amount > 0:
            payment_status = 'paid'
        elif advance > 0:
            payment_status = 'partial'
        else:
            payment_status = 'unpaid'
        
        return JsonResponse({
            'success': True,
            'subtotal': str(subtotal),
            'taxable_amount': str(taxable_amount),
            'tax_amount': str(tax_amount),
            'total_amount': str(total_amount),
            'balance': str(balance),
            'payment_status': payment_status,
            'calculation_details': {
                'subtotal_formula': f"{quantity} × {unit_price} = {subtotal}",
                'taxable_formula': f"{subtotal} - {discount} = {taxable_amount}",
                'tax_formula': f"{taxable_amount} × ({tax_percent}%) = {tax_amount}",
                'total_formula': f"{taxable_amount} + {tax_amount} = {total_amount}",
                'balance_formula': f"{total_amount} - {advance} = {balance}",
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
def transaction_edit(request, pk):
    obj = get_object_or_404(DailySaleTransaction, pk=pk)
    if request.method == "POST":
        form = DailySaleTransactionForm(request.POST, instance=obj, user=request.user)
        # same safe population technique as create
        from accounts.models import Company, UserProfile
        from containers.models import Container, Inventory_List
        cid = request.POST.get("company")
        form.fields["company"].queryset = Company.objects.filter(pk=cid) if cid else Company.objects.none()
        cuid = request.POST.get("customer")
        form.fields["customer"].queryset = UserProfile.objects.filter(pk=cuid) if cuid else UserProfile.objects.none()
        cont_id = request.POST.get("container")
        form.fields["container"].queryset = Container.objects.filter(pk=cont_id) if cont_id else Container.objects.none()
        item_id = request.POST.get("item")
        form.fields["item"].queryset = Inventory_List.objects.filter(pk=item_id) if item_id else Inventory_List.objects.none()

        if form.is_valid():
            try:
                with transaction.atomic():
                    obj = form.save(commit=False)
                    comp = form.cleaned_data.get("_computed", {}) or {}
                    obj.subtotal = comp.get("subtotal", Decimal("0.00"))
                    obj.total_amount = comp.get("total_amount", Decimal("0.00"))
                    obj.balance = comp.get("balance", Decimal("0.00"))
                    obj.save()
                messages.success(request, "Transaction updated.")
                return redirect(reverse("daily_sale:transaction_list"))
            except Exception:
                logger.exception("Error updating transaction")
                messages.error(request, "Failed to update transaction.")
        else:
            messages.error(request, "Validation error.")
    else:
        form = DailySaleTransactionForm(instance=obj, user=request.user)
        # for edit, make current related objects available so select2 initial shows properly
        if obj.company_id:
            form.fields["company"].queryset = form.fields["company"].queryset.filter(pk=obj.company_id) or form.fields["company"].queryset
        if obj.customer_id:
            form.fields["customer"].queryset = form.fields["customer"].queryset.filter(pk=obj.customer_id) or form.fields["customer"].queryset
        if obj.container_id:
            form.fields["container"].queryset = form.fields["container"].queryset.filter(pk=obj.container_id) or form.fields["container"].queryset
        if obj.item_id:
            form.fields["item"].queryset = form.fields["item"].queryset.filter(pk=obj.item_id) or form.fields["item"].queryset

    ajax_urls = {
        "containers": reverse("daily_sale:ajax_containers"),
        "items": reverse("daily_sale:ajax_items"),
        "companies": reverse("daily_sale:ajax_companies"),
        "customers": reverse("daily_sale:ajax_customers"),
    }
    return render(request, "daily_sale/transaction_edit.html", {"form": form, "obj": obj, "ajax_urls": ajax_urls})

@login_required
def transaction_list(request):
    """
    لیست تراکنش‌ها با قابلیت‌های فیلترینگ و جستجوی پیشرفته
    """
    try:
        # دریافت پارامترهای فیلتر
        start_date = parse_date_param(request.GET.get("start_date"))
        end_date = parse_date_param(request.GET.get("end_date"))
        transaction_type = request.GET.get("type", "")
        customer_id = request.GET.get("customer", "")
        company_id = request.GET.get("company", "")
        invoice_number = request.GET.get("invoice", "").strip()
        status_filter = request.GET.get("status", "")
        items_per_page = int(request.GET.get("per_page", 25))
        export_csv = request.GET.get("export") == "csv"
        
        # ساخت کوئری اصلی با select_related برای کارایی بهتر
        qs = DailySaleTransaction.objects.select_related(
            "item", 
            "customer__user", 
            "company", 
            "container"
        ).order_by("-date", "-created_at")
        
        # اعمال فیلترها
        filter_applied = False
        
        if start_date:
            qs = qs.filter(date__gte=start_date)
            filter_applied = True
            
        if end_date:
            qs = qs.filter(date__lte=end_date)
            filter_applied = True
            
        if transaction_type and transaction_type in ['sale', 'purchase', 'return']:
            qs = qs.filter(transaction_type=transaction_type)
            filter_applied = True
            
        if customer_id and customer_id.isdigit():
            qs = qs.filter(customer_id=int(customer_id))
            filter_applied = True
            
        if company_id and company_id.isdigit():
            qs = qs.filter(company_id=int(company_id))
            filter_applied = True
            
        if invoice_number:
            qs = qs.filter(invoice_number__icontains=invoice_number)
            filter_applied = True
            
        # فیلتر بر اساس وضعیت پرداخت
        if status_filter:
            if status_filter == 'paid':
                qs = qs.filter(
                    id__in=DailySaleTransaction.objects.annotate(
                        paid_amount=Coalesce(Sum('payments__amount'), Decimal('0'), output_field=DecimalField())
                    ).filter(total_amount__lte=F('paid_amount')).values('id')
                )
            elif status_filter == 'partial':
                qs = qs.filter(
                    id__in=DailySaleTransaction.objects.annotate(
                        paid_amount=Coalesce(Sum('payments__amount'), Decimal('0'), output_field=DecimalField())
                    ).filter(
                        Q(paid_amount__gt=Decimal('0')) & 
                        Q(paid_amount__lt=F('total_amount'))
                    ).values('id')
                )
            elif status_filter == 'unpaid':
                qs = qs.filter(
                    id__in=DailySaleTransaction.objects.annotate(
                        paid_amount=Coalesce(Sum('payments__amount'), Decimal('0'), output_field=DecimalField())
                    ).filter(paid_amount=Decimal('0')).values('id')
                )
            filter_applied = True
        
        # تعداد کل رکوردها قبل از صفحه‌بندی
        total_count = qs.count()
        
        # محاسبات آماری برای نمایش در کارت‌ها
        stats = {}
        
        # مجموع فروش
        sales_total = qs.filter(transaction_type='sale').aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        stats['total_sales'] = sales_total
        
        # مجموع خرید
        purchases_total = qs.filter(transaction_type='purchase').aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        stats['total_purchases'] = purchases_total
        
        # مجموع برگشت
        returns_total = qs.filter(transaction_type='return').aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        stats['total_returns'] = returns_total
        
        # محاسبه مجموع مانده بدهی
        outstanding_total = Decimal('0')
        outstanding_count = 0
        
        # محاسبه برای هر تراکنش
        for transaction in qs:
            paid_amount = Payment.objects.filter(transaction=transaction).aggregate(
                total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
            )['total'] or Decimal('0')
            
            remaining = transaction.total_amount - paid_amount
            if remaining > Decimal('0'):
                outstanding_total += remaining
                outstanding_count += 1
        
        stats['total_outstanding'] = outstanding_total
        stats['outstanding_count'] = outstanding_count
        
        # تعداد آیتم‌های فروخته شده
        items_sold = qs.filter(transaction_type='sale').aggregate(
            total=Coalesce(Sum('quantity'), 0)
        )['total']
        stats['items_sold'] = items_sold
        
        # میانگین مبلغ تراکنش
        if total_count > 0:
            avg_transaction = (sales_total + purchases_total + returns_total) / total_count
        else:
            avg_transaction = Decimal('0')
        stats['avg_transaction'] = avg_transaction
        
        # اگر export درخواست شده باشد
        if export_csv:
            return export_transactions_to_csv(qs)
        
        # صفحه‌بندی
        paginator = Paginator(qs, items_per_page)
        page_number = request.GET.get("page", 1)
        
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        
        # محاسبه مبالغ پرداخت شده برای هر تراکنش در صفحه جاری
        transactions_with_payments = []
        for transaction in page_obj:
            paid_amount = Payment.objects.filter(transaction=transaction).aggregate(
                total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
            )['total'] or Decimal('0')
            
            remaining = transaction.total_amount - paid_amount
            
            # تعیین وضعیت پرداخت
            if paid_amount == Decimal('0'):
                payment_status = 'unpaid'
                status_class = 'danger'
            elif remaining == Decimal('0'):
                payment_status = 'paid'
                status_class = 'success'
            else:
                payment_status = 'partial'
                status_class = 'warning'
            
            # اضافه کردن فیلدهای محاسبه شده به آبجکت
            transaction.paid_amount = paid_amount
            transaction.remaining_balance = remaining
            transaction.payment_status = payment_status
            transaction.status_class = status_class
            transaction.payment_percentage = int((paid_amount / transaction.total_amount * 100)) if transaction.total_amount > 0 else 0
            
            transactions_with_payments.append(transaction)
        
        # دریافت لیست مشتریان و شرکت‌ها برای dropdown فیلترها
        customers = UserProfile.objects.filter(
            daily_transactions__isnull=False
        ).distinct().order_by('user__first_name')[:50]
        
        companies = Company.objects.filter(
            daily_transactions__isnull=False
        ).distinct().order_by('name')[:50]
        
        # فرمت تاریخ برای استفاده در template
        start_date_str = start_date.strftime("%Y-%m-%d") if start_date else ""
        end_date_str = end_date.strftime("%Y-%m-%d") if end_date else ""
        
        # تاریخ 30 روز گذشته برای فیلتر پیش‌فرض
        thirty_days_ago = (datetime.now() - timedelta(days=30)).date()
        
        context = {
            "page_obj": page_obj,
            "transactions": transactions_with_payments,
            "start_date": start_date_str,
            "end_date": end_date_str,
            "transaction_type_filter": transaction_type,
            "customer_filter": customer_id,
            "company_filter": company_id,
            "invoice_filter": invoice_number,
            "status_filter": status_filter,
            "per_page": items_per_page,
            "total_count": total_count,
            "stats": stats,
            "customers": customers,
            "companies": companies,
            "filter_applied": filter_applied,
            "today": datetime.now().date(),
            "thirty_days_ago": thirty_days_ago,
            "paginator": paginator,
            "current_page": page_obj.number,
        }
        
        # درخواست AJAX (برای auto-refresh یا بارگذاری جزئی)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            data = {
                'success': True,
                'total_count': total_count,
                'total_sales': str(stats['total_sales']),
                'total_outstanding': str(stats['total_outstanding']),
                'page_count': paginator.num_pages,
                'current_page': page_obj.number,
                'has_previous': page_obj.has_previous(),
                'has_next': page_obj.has_next(),
                'previous_page_number': page_obj.previous_page_number() if page_obj.has_previous() else None,
                'next_page_number': page_obj.next_page_number() if page_obj.has_next() else None,
            }
            return JsonResponse(data)
        
        return render(request, "daily_sale/transaction_list.html", context)
        
    except Exception as e:
        logger.error(f"Error in transaction_list view: {str(e)}", exc_info=True)
        
        # بازگشت به حالت پیش‌فرض در صورت خطا
        try:
            qs = DailySaleTransaction.objects.select_related(
                "item", "customer__user", "company", "container"
            ).order_by("-date", "-created_at")[:100]
            
            paginator = Paginator(qs, 25)
            page_obj = paginator.page(1)
            
            # محاسبه ساده stats
            stats = {
                'total_sales': Decimal('0'),
                'total_outstanding': Decimal('0'),
                'items_sold': 0,
                'avg_transaction': Decimal('0'),
            }
            
            context = {
                "page_obj": page_obj,
                "transactions": page_obj.object_list,
                "start_date": "",
                "end_date": "",
                "stats": stats,
                "total_count": qs.count(),
                "error": True,
                "error_message": "An error occurred while loading transactions.",
            }
            return render(request, "daily_sale/transaction_list.html", context)
        except Exception as inner_e:
            logger.error(f"Error in transaction_list fallback: {str(inner_e)}")
            return render(request, "daily_sale/transaction_list.html", {
                "error": True,
                "error_message": "Unable to load transactions. Please contact support."
            })


def export_transactions_to_csv(queryset):
    """
    خروجی CSV از تراکنش‌ها
    """
    import csv
    from django.http import HttpResponse
    from django.utils.encoding import smart_str
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="transactions_export.csv"'
    
    writer = csv.writer(response)
    
    # نوشتن هدر
    writer.writerow([
        smart_str('Invoice Number'),
        smart_str('Date'),
        smart_str('Customer'),
        smart_str('Type'),
        smart_str('Item'),
        smart_str('Quantity'),
        smart_str('Unit Price'),
        smart_str('Discount'),
        smart_str('Tax'),
        smart_str('Total Amount'),
        smart_str('Advance'),
        smart_str('Balance'),
        smart_str('Paid Amount'),
        smart_str('Remaining Balance'),
        smart_str('Status'),
        smart_str('Description'),
    ])
    
    # نوشتن داده‌ها
    for transaction in queryset:
        paid_amount = Payment.objects.filter(transaction=transaction).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0')
        
        remaining = transaction.total_amount - paid_amount
        
        if paid_amount == Decimal('0'):
            status = 'Unpaid'
        elif remaining == Decimal('0'):
            status = 'Paid'
        else:
            status = 'Partial'
        
        customer_name = transaction.customer.user.get_full_name() if transaction.customer and transaction.customer.user else 'N/A'
        item_name = transaction.item.product_name if transaction.item else 'N/A'
        
        writer.writerow([
            smart_str(transaction.invoice_number or ''),
            smart_str(transaction.date.strftime('%Y-%m-%d') if transaction.date else ''),
            smart_str(customer_name),
            smart_str(transaction.get_transaction_type_display()),
            smart_str(item_name),
            smart_str(transaction.quantity),
            smart_str(transaction.unit_price),
            smart_str(transaction.discount),
            smart_str(transaction.tax),
            smart_str(transaction.total_amount),
            smart_str(transaction.advance),
            smart_str(transaction.balance),
            smart_str(paid_amount),
            smart_str(remaining),
            smart_str(status),
            smart_str(transaction.description or ''),
        ])
    
    return response
@login_required
def transaction_detail(request, pk):
    tx = get_object_or_404(DailySaleTransaction.objects.select_related("item", "customer__user", "company", "container"), pk=pk)
    payments = tx.payments.order_by("-date")
    paid_total = payments.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    remaining = (tx.total_amount or Decimal("0.00")) - paid_total
    if request.method == "POST":
        pform = PaymentForm(request.POST)
        if pform.is_valid():
            p = pform.save(commit=False)
            p.transaction = tx
            p.created_by = request.user
            p.save()
            messages.success(request, "Payment recorded.")
            return redirect(reverse("daily_sale:transaction_detail", args=[tx.pk]))
        else:
            messages.error(request, "Payment invalid.")
    else:
        pform = PaymentForm(initial={"date": timezone.now().date()})
    return render(request, "daily_sale/transaction_detail.html", {"tx": tx, "payments": payments, "paid_total": paid_total, "remaining": remaining, "pform": pform})


@login_required
def daily_summary(request):
    """
    Daily summary with all real-time calculations
    """
    try:
        # Get date parameters from GET request
        start_date_str = request.GET.get("start_date")
        end_date_str = request.GET.get("end_date")
        
        # Default date range (last 30 days)
        today = timezone.now().date()
        default_end_date = today
        default_start_date = today - timedelta(days=30)
        
        # Parse date strings
        start_date = default_start_date
        end_date = default_end_date
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass  # Keep default value in case of error
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass  # Keep default value in case of error
        
        # Ensure valid date range (start_date <= end_date)
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        
        # Limit the range to 365 days maximum
        if (end_date - start_date).days > 365:
            start_date = end_date - timedelta(days=365)
        
        # 1. Get overall sales summary for the selected date range
        period_summary = get_sales_summary(start_date, end_date)
        
        # 2. Get daily timeseries data for the selected range (grouped by day)
        daily_series = sales_timeseries(start_date, end_date, group_by="day")
        
        # 3. Calculate total and count of Cash In (payments received)
        cash_in_data = Payment.objects.filter(
            date__range=[start_date, end_date]
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        cash_in_total = cash_in_data['total'] or Decimal('0.00')
        cash_in_count = cash_in_data['count'] or 0
        
        # 4. Calculate total and count of Cash Out (purchases, returns, expenses)
        cash_out_data = DailySaleTransaction.objects.filter(
            date__range=[start_date, end_date],
            transaction_type__in=['purchase', 'return']
        ).aggregate(
            total=Sum('total_amount'),
            count=Count('id')
        )
        cash_out_total = cash_out_data['total'] or Decimal('0.00')
        cash_out_count = cash_out_data['count'] or 0
        
        # 5. Calculate net profit (Cash In - Cash Out)
        net_profit = cash_in_total - cash_out_total
        
        # 6. Calculate percentage distribution of Cash In and Cash Out
        total_revenue = cash_in_total + abs(cash_out_total)
        cash_in_percentage = 0
        cash_out_percentage = 0
        if total_revenue > 0:
            cash_in_percentage = (cash_in_total / total_revenue * 100)
            cash_out_percentage = (abs(cash_out_total) / total_revenue * 100)
        
        # 7. Calculate profit margin
        profit_margin = 0
        if period_summary['total_sales'] > 0:
            profit_margin = (period_summary['net_revenue'] / period_summary['total_sales'] * 100)
        
        # 8. Calculate average daily sales
        days_count = len(daily_series)
        avg_daily_sales = period_summary['total_sales'] / days_count if days_count > 0 else Decimal('0.00')
        
        # 9. Find the best sales day (highest total sales)
        best_day = {'date': start_date, 'total_sales': Decimal('0.00')}
        for day in daily_series:
            if day['total_sales'] > best_day['total_sales']:
                best_day = day
        
        # 10. Calculate growth rate based on the first and last day sales
        growth_rate = 0
        if len(daily_series) >= 2:
            first_day = daily_series[-1]['total_sales']  # Oldest
            last_day = daily_series[0]['total_sales']    # Most recent
            if first_day > 0:
                growth_rate = ((last_day - first_day) / first_day * 100)
        
        # 11. Prepare chart data for rendering
        chart_labels = []
        chart_sales = []
        chart_cash_in = []
        chart_cash_out = []
        
        for day in daily_series:
            chart_labels.append(day['date'].strftime('%b %d'))
            chart_sales.append(float(day['total_sales']))
            daily_cash_in = Payment.objects.filter(
                date=day['date']
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            chart_cash_in.append(float(daily_cash_in))
            daily_cash_out = DailySaleTransaction.objects.filter(
                date=day['date'],
                transaction_type__in=['purchase', 'return']
            ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
            chart_cash_out.append(float(daily_cash_out))
        
        # 12. Calculate quick date filters (Yesterday, This Week, This Month, etc.)
        yesterday = today - timedelta(days=1)
        week_start = today - timedelta(days=(today.weekday() + 2) % 7)
        month_start = today.replace(day=1)
        last_month_end = month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        year_start = today.replace(month=1, day=1)
        
        # 13. Enhance daily series with additional data for each day
        enhanced_daily_series = []
        for i, day in enumerate(daily_series):
            date = day['date']
            is_today = date == today
            
            daily_cash_in = Payment.objects.filter(date=date).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0.00')
            
            daily_cash_out = DailySaleTransaction.objects.filter(
                date=date,
                transaction_type__in=['purchase', 'return']
            ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
            
            daily_profit = daily_cash_in - daily_cash_out
            transaction_count = DailySaleTransaction.objects.filter(
                date=date,
                transaction_type='sale'
            ).count()
            avg_sale = day['total_sales'] / transaction_count if transaction_count > 0 else Decimal('0.00')
            
            items_sold = DailySaleTransaction.objects.filter(
                date=date,
                transaction_type='sale'
            ).aggregate(total=Sum('quantity'))['total'] or 0
            
            profit_trend = None
            profit_trend_class = ''
            if i < len(daily_series) - 1:
                prev_day = daily_series[i + 1]
                prev_profit = prev_day['total_sales'] - daily_cash_out
                if prev_profit != 0:
                    profit_trend = ((daily_profit - prev_profit) / prev_profit * 100)
                    profit_trend_class = 'trend-up' if profit_trend > 0 else 'trend-down'
            
            enhanced_day = {
                **day,
                'is_today': is_today,
                'cash_in': daily_cash_in,
                'cash_out': daily_cash_out,
                'profit': daily_profit,
                'avg_sale': avg_sale,
                'items_sold': items_sold,
                'profit_trend': profit_trend,
                'profit_trend_class': profit_trend_class,
            }
            enhanced_daily_series.append(enhanced_day)
        
        # 14. Prepare context for template rendering
        context = {
            'start_date': start_date,
            'end_date': end_date,
            'period_summary': period_summary,
            'daily_series': enhanced_daily_series,
            'cash_in_total': cash_in_total,
            'cash_out_total': cash_out_total,
            'cash_in_count': cash_in_count,
            'cash_out_count': cash_out_count,
            'cash_in_percentage': cash_in_percentage,
            'cash_out_percentage': cash_out_percentage,
            'profit_margin': profit_margin,
            'profit_percentage': min(100, max(0, profit_margin)),
            'sales_percentage': min(100, cash_in_percentage),
            'chart_labels': json.dumps(chart_labels),
            'chart_sales': json.dumps(chart_sales),
            'chart_cash_in': json.dumps(chart_cash_in),
            'chart_cash_out': json.dumps(chart_cash_out),
            'today': today,
            'yesterday': yesterday,
            'week_start': week_start,
            'month_start': month_start,
            'last_month_start': last_month_start,
            'last_month_end': last_month_end,
            'year_start': year_start,
            'avg_daily_sales': avg_daily_sales,
            'best_day': best_day,
            'growth_rate': growth_rate,
            'net_profit': net_profit,
        }
        
        # 15. Return JSON response if it's an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'total_sales': str(period_summary['total_sales']),
                'total_purchases': str(period_summary['total_purchases']),
                'net_revenue': str(period_summary['net_revenue']),
                'cash_in_total': str(cash_in_total),
                'cash_out_total': str(cash_out_total),
                'transactions_count': period_summary['transactions_count'],
                'items_sold': period_summary['items_sold'],
                'chart_labels': chart_labels,
                'chart_sales': chart_sales,
                'chart_cash_in': chart_cash_in,
            })
        
        return render(request, "daily_sale/daily_summary.html", context)
        
    except Exception as e:
        print(f"Error in daily_summary: {str(e)}")
        # Fallback in case of error
        today = timezone.now().date()
        start_date = today - timedelta(days=30)
        
        context = {
            'start_date': start_date,
            'end_date': today,
            'period_summary': {
                'total_sales': Decimal('0.00'),
                'total_purchases': Decimal('0.00'),
                'net_revenue': Decimal('0.00'),
                'transactions_count': 0,
                'items_sold': 0,
            },
            'daily_series': [],
            'cash_in_total': Decimal('0.00'),
            'cash_out_total': Decimal('0.00'),
            'error': True,
            'error_message': 'خطا در بارگذاری داده‌ها',
        }
        return render(request, "daily_sale/daily_summary.html", context)

@login_required
def daily_summary(request):
    """
    Daily summary with all real-time calculations - OPTIMIZED VERSION
    """
    try:
        # Get date parameters from GET request
        start_date_str = request.GET.get("start_date")
        end_date_str = request.GET.get("end_date")
        
        # Default date range (last 30 days)
        today = timezone.now().date()
        default_end_date = today
        default_start_date = today - timedelta(days=30)
        
        # Parse date strings
        start_date = default_start_date
        end_date = default_end_date
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                logger.warning(f"Invalid start_date: {start_date_str}")
                pass
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            except ValueError:
                logger.warning(f"Invalid end_date: {end_date_str}")
                pass
        
        # Ensure valid date range (start_date <= end_date)
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        
        # Limit the range to 365 days maximum
        if (end_date - start_date).days > 365:
            start_date = end_date - timedelta(days=365)
        
        # 1. استفاده از DailySummary به جای محاسبات real-time (بهینه‌سازی)
        daily_summaries = DailySummary.objects.filter(
            date__range=[start_date, end_date]
        ).order_by('date')
        
        # اگر داده‌ای در DailySummary نداریم، از محاسبات real-time استفاده کنیم
        use_real_time = not daily_summaries.exists()
        
        if use_real_time:
            logger.info(f"Using real-time calculations for date range {start_date} to {end_date}")
            # از منطق قدیمی استفاده می‌کنیم
            return get_real_time_daily_summary(request, start_date, end_date, today)
        
        logger.info(f"Using cached DailySummary for date range {start_date} to {end_date}")
        
        # 2. محاسبه آمار دوره از DailySummary
        period_stats = daily_summaries.aggregate(
            total_sales=Sum('total_sales'),
            total_purchases=Sum('total_purchases'),
            total_profit=Sum('total_profit'),
            total_balance=Sum('net_balance'),
            total_transactions=Sum('transactions_count'),
            total_items_sold=Sum('items_sold'),
            total_customers=Sum('customers_count')
        )
        
        # 3. Calculate Cash In from Payments
        cash_in_data = Payment.objects.filter(
            date__range=[start_date, end_date]
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        cash_in_total = cash_in_data['total'] or Decimal('0.00')
        cash_in_count = cash_in_data['count'] or 0
        
        # 4. Calculate Cash Out from transactions
        cash_out_data = DailySaleTransaction.objects.filter(
            date__range=[start_date, end_date],
            transaction_type__in=['purchase', 'return']
        ).aggregate(
            total=Sum('total_amount'),
            count=Count('id')
        )
        cash_out_total = cash_out_data['total'] or Decimal('0.00')
        cash_out_count = cash_out_data['count'] or 0
        
        # 5. Calculate net profit
        net_profit = cash_in_total - cash_out_total
        
        # 6. Prepare daily series from DailySummary
        daily_series = []
        chart_labels = []
        chart_sales = []
        chart_cash_in = []
        chart_cash_out = []
        
        for summary in daily_summaries:
            date = summary.date
            daily_cash_in = Payment.objects.filter(
                date=date
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            
            daily_cash_out = DailySaleTransaction.objects.filter(
                date=date,
                transaction_type__in=['purchase', 'return']
            ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
            
            day_data = {
                'date': date,
                'total_sales': summary.total_sales,
                'total_purchases': summary.total_purchases,
                'total_profit': summary.total_profit,
                'net_balance': summary.net_balance,
                'transactions_count': summary.transactions_count,
                'items_sold': summary.items_sold,
                'customers_count': summary.customers_count,
                'is_today': date == today,
                'cash_in': daily_cash_in,
                'cash_out': daily_cash_out,
            }
            daily_series.append(day_data)
            
            # Chart data
            chart_labels.append(date.strftime('%b %d'))
            chart_sales.append(float(summary.total_sales))
            chart_cash_in.append(float(daily_cash_in))
            chart_cash_out.append(float(daily_cash_out))
        
        # 7. Calculate additional metrics
        total_sales = period_stats['total_sales'] or Decimal('0.00')
        total_revenue = cash_in_total + abs(cash_out_total)
        
        cash_in_percentage = 0
        cash_out_percentage = 0
        if total_revenue > 0:
            cash_in_percentage = (cash_in_total / total_revenue * 100)
            cash_out_percentage = (abs(cash_out_total) / total_revenue * 100)
        
        profit_margin = 0
        if total_sales > 0:
            total_profit = period_stats['total_profit'] or Decimal('0.00')
            profit_margin = (total_profit / total_sales * 100)
        
        # 8. Calculate averages and best day
        days_count = len(daily_series)
        avg_daily_sales = total_sales / days_count if days_count > 0 else Decimal('0.00')
        
        best_day = {'date': start_date, 'total_sales': Decimal('0.00')}
        for day in daily_series:
            if day['total_sales'] > best_day['total_sales']:
                best_day = day
        
        # 9. Calculate growth rate
        growth_rate = 0
        if len(daily_series) >= 2:
            first_day = daily_series[0]['total_sales']
            last_day = daily_series[-1]['total_sales']
            if first_day > 0:
                growth_rate = ((last_day - first_day) / first_day * 100)
        
        # 10. Quick date filters
        yesterday = today - timedelta(days=1)
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        last_month_end = month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        year_start = today.replace(month=1, day=1)
        
        # 11. Prepare context
        context = {
            'start_date': start_date,
            'end_date': end_date,
            'period_summary': {
                'total_sales': total_sales,
                'total_purchases': period_stats['total_purchases'] or Decimal('0.00'),
                'net_revenue': total_sales - (period_stats['total_purchases'] or Decimal('0.00')),
                'total_profit': period_stats['total_profit'] or Decimal('0.00'),
                'net_balance': period_stats['total_balance'] or Decimal('0.00'),
                'transactions_count': period_stats['total_transactions'] or 0,
                'items_sold': period_stats['total_items_sold'] or 0,
                'customers_count': period_stats['total_customers'] or 0,
            },
            'daily_series': daily_series,
            'cash_in_total': cash_in_total,
            'cash_out_total': cash_out_total,
            'cash_in_count': cash_in_count,
            'cash_out_count': cash_out_count,
            'cash_in_percentage': cash_in_percentage,
            'cash_out_percentage': cash_out_percentage,
            'profit_margin': profit_margin,
            'profit_percentage': min(100, max(0, profit_margin)),
            'sales_percentage': min(100, cash_in_percentage),
            'chart_labels': json.dumps(chart_labels),
            'chart_sales': json.dumps(chart_sales),
            'chart_cash_in': json.dumps(chart_cash_in),
            'chart_cash_out': json.dumps(chart_cash_out),
            'today': today,
            'yesterday': yesterday,
            'week_start': week_start,
            'month_start': month_start,
            'last_month_start': last_month_start,
            'last_month_end': last_month_end,
            'year_start': year_start,
            'avg_daily_sales': avg_daily_sales,
            'best_day': best_day,
            'growth_rate': growth_rate,
            'net_profit': net_profit,
            'using_cached': True,
        }

        return render(request, "daily_sale/daily_summary.html", context)
        
    except Exception as e:
        logger.error(f"Error in daily_summary: {str(e)}")
        today = timezone.now().date()
        start_date = today - timedelta(days=30)
        
        context = {
            'start_date': start_date,
            'end_date': today,
            'period_summary': {
                'total_sales': Decimal('0.00'),
                'total_purchases': Decimal('0.00'),
                'net_revenue': Decimal('0.00'),
                'transactions_count': 0,
                'items_sold': 0,
            },
            'daily_series': [],
            'cash_in_total': Decimal('0.00'),
            'cash_out_total': Decimal('0.00'),
            'error': True,
            'error_message': 'خطا در بارگذاری داده‌ها',
        }
        return render(request, "daily_sale/daily_summary.html", context)
    

@login_required
@require_GET
def generate_daily_report(request):
    """
    تولید و دانلود گزارش JSON
    """
    try:
        # دریافت پارامترهای تاریخ (همان پارامترهای daily_summary)
        start_date_str = request.GET.get("start_date")
        end_date_str = request.GET.get("end_date")
        
        # اگر تاریخ ارسال نشد، از تاریخ‌های جلسه استفاده کن
        if not start_date_str or not end_date_str:
            start_date_str = request.session.get('report_start_date', '')
            end_date_str = request.session.get('report_end_date', '')
        
        # تبدیل تاریخ‌ها
        from datetime import datetime
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        
        # 1. محاسبه آمار دوره (کوئری اصلی شما)
        from django.db.models import Sum, Count, Avg, Max, Min
        
        # اگر DailySummary دارید
        daily_summaries = DailySummary.objects.filter(
            date__range=[start_date, end_date]
        )
        
        # محاسبه آمار
        period_stats = daily_summaries.aggregate(
            total_sales=Sum('total_sales'),
            total_purchases=Sum('total_purchases'),
            total_profit=Sum('total_profit'),
            total_transactions=Sum('transactions_count'),
            total_items_sold=Sum('items_sold'),
            total_customers=Sum('customers_count'),
        )
        
        # 2. محاسبه Cash In
        cash_in_data = Payment.objects.filter(
            date__range=[start_date, end_date]
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        cash_in_total = cash_in_data['total'] or Decimal('0.00')
        
        # 3. محاسبه Cash Out
        cash_out_data = DailySaleTransaction.objects.filter(
            date__range=[start_date, end_date],
            transaction_type__in=['purchase', 'return']
        ).aggregate(
            total=Sum('total_amount'),
            count=Count('id')
        )
        cash_out_total = cash_out_data['total'] or Decimal('0.00')
        
        # 4. محاسبه Net Profit
        net_profit = cash_in_total - cash_out_total
        
        # 5. محاسبه Profit Margin
        profit_margin = Decimal('0.00')
        if period_stats['total_sales'] and period_stats['total_sales'] > 0:
            profit_margin = (period_stats['total_profit'] / period_stats['total_sales'] * 100)
        
        # 6. محاسبه Avg Daily Sales
        days_count = (end_date - start_date).days + 1
        avg_daily_sales = period_stats['total_sales'] / days_count if days_count > 0 else Decimal('0.00')
        
        # 7. پیدا کردن Best Day
        best_day_obj = daily_summaries.order_by('-total_sales').first()
        best_day = {
            'date': best_day_obj.date if best_day_obj else start_date,
            'total_sales': best_day_obj.total_sales if best_day_obj else Decimal('0.00')
        }
        
        # 8. محاسبه Growth Rate
        growth_rate = Decimal('0.00')
        if daily_summaries.count() >= 2:
            first_day = daily_summaries.order_by('date').first()
            last_day = daily_summaries.order_by('-date').first()
            if first_day.total_sales and first_day.total_sales > 0:
                growth_rate = ((last_day.total_sales - first_day.total_sales) / first_day.total_sales * 100)
        
        # 9. آماده‌سازی داده‌های گزارش
        report_data = {
            'report_type': 'Daily Summary Report',
            'date_range': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d'),
                'days': daily_summaries.count()
            },
            'summary': {
                'total_sales': float(period_stats['total_sales'] or Decimal('0.00')),
                'total_purchases': float(period_stats['total_purchases'] or Decimal('0.00')),
                'net_revenue': float((period_stats['total_sales'] or Decimal('0.00')) - (period_stats['total_purchases'] or Decimal('0.00'))),
                'transactions_count': period_stats['total_transactions'] or 0,
                'items_sold': period_stats['total_items_sold'] or 0,
                'customers_count': period_stats['total_customers'] or 0,
                'cash_in_total': float(cash_in_total),
                'cash_out_total': float(cash_out_total),
                'net_profit': float(net_profit),
                'profit_margin': float(profit_margin),
                'avg_daily_sales': float(avg_daily_sales),
            },
            'best_day': {
                'date': best_day['date'].strftime('%Y-%m-%d'),
                'total_sales': float(best_day['total_sales'])
            },
            'growth_rate': float(growth_rate),
            'generated_at': datetime.now().isoformat(),
            'generated_by': 'Daily Summary Dashboard'
        }
        
        # 10. بازگرداندن JSON به عنوان فایل قابل دانلود
        response = HttpResponse(
            json.dumps(report_data, indent=2, ensure_ascii=False),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="daily_summary_report_{start_date}_{end_date}.json"'
        return response
        
    except Exception as e:
        # در صورت خطا
        error_data = {
            'error': True,
            'message': str(e),
            'generated_at': datetime.now().isoformat()
        }
        return JsonResponse(error_data, status=400)


def get_real_time_daily_summary(request, start_date, end_date, today):
    """
    Fallback function when DailySummary data is not available
    """
    try:
        # استفاده از توابع utils
        period_summary = get_sales_summary(start_date, end_date)
        
        # محاسبه سری زمانی
        daily_timeseries = sales_timeseries(start_date, end_date, group_by="day")
        
        # Cash In and Out محاسبات
        cash_in_data = Payment.objects.filter(
            date__range=[start_date, end_date]
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        cash_in_total = cash_in_data['total'] or Decimal('0.00')
        
        cash_out_data = DailySaleTransaction.objects.filter(
            date__range=[start_date, end_date],
            transaction_type__in=['purchase', 'return']
        ).aggregate(
            total=Sum('total_amount'),
            count=Count('id')
        )
        cash_out_total = cash_out_data['total'] or Decimal('0.00')
        
        # آماده‌سازی داده‌های چارت
        chart_labels = []
        chart_sales = []
        
        for day in daily_timeseries:
            chart_labels.append(day['date'].strftime('%b %d'))
            chart_sales.append(float(day['total_sales']))
        
        # Quick date filters
        yesterday = today - timedelta(days=1)
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        last_month_end = month_start - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        year_start = today.replace(month=1, day=1)
        
        context = {
            'start_date': start_date,
            'end_date': end_date,
            'period_summary': period_summary,
            'daily_series': daily_timeseries,
            'cash_in_total': cash_in_total,
            'cash_out_total': cash_out_total,
            'cash_in_count': cash_in_data['count'] or 0,
            'cash_out_count': cash_out_data['count'] or 0,
            'chart_labels': json.dumps(chart_labels),
            'chart_sales': json.dumps(chart_sales),
            'today': today,
            'yesterday': yesterday,
            'week_start': week_start,
            'month_start': month_start,
            'last_month_start': last_month_start,
            'last_month_end': last_month_end,
            'year_start': year_start,
            'using_cached': False,
        }
        
        return render(request, "daily_sale/daily_summary.html", context)
        
    except Exception as e:
        logger.error(f"Error in get_real_time_daily_summary: {e}")
        raise


@login_required
def outstanding_view(request):
    """
    Outstanding customers with PostgreSQL raw queries
    """
    try:
        # 1. Get total outstanding summary
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(total_debt), 0) as total_outstanding,
                    COALESCE(COUNT(*), 0) as customers_count,
                    COALESCE(AVG(total_debt), 0) as avg_debt,
                    COALESCE(AVG(transactions_count), 0) as avg_transactions
                FROM daily_sale_outstandingcustomer
                WHERE total_debt > 0
            """)
            summary = cursor.fetchone()
            total_outstanding = Decimal(str(summary[0])) if summary[0] else Decimal('0')
            customers_count = summary[1] or 0
            avg_debt = Decimal(str(summary[2])) if summary[2] else Decimal('0')
            avg_transactions = Decimal(str(summary[3])) if summary[3] else Decimal('0')
        
        # 2. Get recent additions (last 7 days)
        week_ago = timezone.now().date() - timedelta(days=7)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    COUNT(*) as recent_count,
                    COALESCE(SUM(total_debt), 0) as recent_amount
                FROM daily_sale_outstandingcustomer
                WHERE total_debt > 0 
                AND updated_at >= %s
            """, [week_ago])
            recent = cursor.fetchone()
            recent_count = recent[0] or 0
            recent_amount = Decimal(str(recent[1])) if recent[1] else Decimal('0')
        
        # 3. Get oldest debt
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    MAX(last_transaction) as oldest_date,
                    COALESCE(SUM(total_debt), 0) as oldest_amount
                FROM daily_sale_outstandingcustomer
                WHERE total_debt > 0 
                AND last_transaction IS NOT NULL
            """)
            oldest = cursor.fetchone()
            oldest_date = oldest[0]
            oldest_amount = Decimal(str(oldest[1])) if oldest[1] else Decimal('0')
            
            # Calculate days
            oldest_days = 0
            if oldest_date:
                oldest_days = (timezone.now().date() - oldest_date).days
        
        # 4. Get detailed customer data
        outstanding_customers = []
        total_amount = Decimal('0')
        total_paid = Decimal('0')
        total_discount = Decimal('0')
        total_remaining = Decimal('0')
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    oc.customer_id,
                    COALESCE(up.user_id, 0) as user_id,
                    COALESCE(u.first_name || ' ' || u.last_name, up.display_name, 'Unknown') as full_name,
                    COALESCE(u.email, '') as email,
                    COALESCE(up.phone, '') as phone,
                    oc.total_debt,
                    oc.transactions_count,
                    oc.last_transaction,
                    oc.updated_at
                FROM daily_sale_oldtransactions oc
                LEFT JOIN accounts_userprofile up ON oc.customer_id = up.id
                LEFT JOIN auth_user u ON up.user_id = u.id
                WHERE oc.total_debt > 0
                ORDER BY oc.total_debt DESC
            """)
            
            for row in cursor.fetchall():
                customer_id = row[0]
                user_id = row[1]
                full_name = row[2] or 'Unknown'
                email = row[3] or ''
                phone = row[4] or ''
                total_debt = Decimal(str(row[5])) if row[5] else Decimal('0')
                transactions_count = row[6] or 0
                last_transaction = row[7]
                updated_at = row[8]
                
                # Get customer's transactions
                with connection.cursor() as tx_cursor:
                    tx_cursor.execute("""
                        SELECT 
                            dst.id,
                            dst.invoice_number,
                            dst.date,
                            dst.total_amount,
                            dst.discount,
                            dst.balance,
                            COALESCE(il.product_name, 'N/A') as item_name,
                            COALESCE(c.name, 'N/A') as container_name,
                            COALESCE(SUM(p.amount), 0) as paid_amount
                        FROM daily_sale_dailysaletransaction dst
                        LEFT JOIN containers_inventory_list il ON dst.item_id = il.id
                        LEFT JOIN containers_container c ON dst.container_id = c.id
                        LEFT JOIN daily_sale_payment p ON dst.id = p.transaction_id
                        WHERE dst.customer_id = %s 
                        AND dst.balance > 0
                        GROUP BY dst.id, il.product_name, c.name
                        ORDER BY dst.date DESC
                    """, [customer_id])
                    
                    transactions = []
                    customer_total = Decimal('0')
                    customer_paid = Decimal('0')
                    customer_discount = Decimal('0')
                    
                    for tx in tx_cursor.fetchall():
                        tx_id = tx[0]
                        invoice = tx[1]
                        tx_date = tx[2]
                        tx_total = Decimal(str(tx[3])) if tx[3] else Decimal('0')
                        tx_discount = Decimal(str(tx[4])) if tx[4] else Decimal('0')
                        tx_balance = Decimal(str(tx[5])) if tx[5] else Decimal('0')
                        item_name = tx[6]
                        container_name = tx[7]
                        paid_amount = Decimal(str(tx[8])) if tx[8] else Decimal('0')
                        
                        transactions.append({
                            'id': tx_id,
                            'invoice_number': invoice,
                            'date': tx_date,
                            'total_amount': tx_total,
                            'discount': tx_discount,
                            'paid_amount': paid_amount,
                            'remaining': tx_balance,
                            'item': item_name,
                            'container': container_name,
                        })
                        
                        customer_total += tx_total
                        customer_paid += paid_amount
                        customer_discount += tx_discount
                
                # Calculate percentages and levels
                remaining_amount = customer_total - customer_paid - customer_discount
                payment_percentage = (customer_paid / customer_total * 100) if customer_total > 0 else 0
                
                # Determine debt level
                if remaining_amount > Decimal('1000'):
                    debt_level = 'high'
                    debt_class = 'debt-high'
                elif remaining_amount > Decimal('100'):
                    debt_level = 'medium'
                    debt_class = 'debt-medium'
                else:
                    debt_level = 'low'
                    debt_class = 'debt-low'
                
                # Calculate due days
                due_days = 0
                if last_transaction:
                    due_days = (timezone.now().date() - last_transaction).days
                
                # Prepare customer data
                customer_data = {
                    'id': customer_id,
                    'full_name': full_name,
                    'initials': ''.join([n[0] for n in full_name.split()[:2]]).upper(),
                    'email': email,
                    'phone': phone,
                    'is_active': True,
                    'transactions_count': transactions_count,
                    'total_amount': customer_total,
                    'paid_amount': customer_paid,
                    'discount_amount': customer_discount,
                    'remaining_amount': remaining_amount,
                    'payment_percentage': payment_percentage,
                    'debt_level': debt_level,
                    'debt_class': debt_class,
                    'due_days': due_days,
                    'last_transaction': {
                        'date': last_transaction,
                        'invoice': transactions[0]['invoice_number'] if transactions else 'N/A',
                        'item': transactions[0]['item'] if transactions else 'N/A',
                    },
                    'transactions': transactions,
                }
                
                outstanding_customers.append(customer_data)
                
                # Update totals
                total_amount += customer_total
                total_paid += customer_paid
                total_discount += customer_discount
                total_remaining += remaining_amount
        
        # Pagination
        paginator = Paginator(outstanding_customers, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        context = {
            'page_obj': page_obj,
            'paginator': paginator,
            'outstanding_data': page_obj.object_list,
            'total_outstanding': total_outstanding,
            'customers_count': customers_count,
            'avg_debt': avg_debt,
            'avg_transactions': avg_transactions,
            'recent_count': recent_count,
            'recent_amount': recent_amount,
            'oldest_days': oldest_days,
            'oldest_amount': oldest_amount,
            'total_amount': total_amount,
            'total_paid': total_paid,
            'total_discount': total_discount,
            'total_remaining': total_remaining,
        }
        return render(request, "daily_sale/old_transactions.html", context)
        
    except Exception as e:
        print(f"Outstanding view error: {e}")
        return render(request, "daily_sale/old_transactions.html", {
            'error': True,
            'error_message': 'Error loading outstanding customers'
        })


@login_required
def cleared_transactions(request):
    """
    Display all fully paid/cleared transactions
    """
    try:
        # Get filter parameters
        period = request.GET.get('period', 'month')
        customer_id = request.GET.get('customer')
        payment_method = request.GET.get('method')
        settlement_type = request.GET.get('type')
        sort_by = request.GET.get('sort', 'date_desc')
        
        # Calculate date range based on period
        today = timezone.now().date()
        
        if period == 'today':
            start_date = today
            end_date = today
        elif period == 'yesterday':
            start_date = today - timedelta(days=1)
            end_date = start_date
        elif period == 'week':
            start_date = today - timedelta(days=today.weekday())
            end_date = today
        elif period == 'month':
            start_date = today.replace(day=1)
            end_date = today
        elif period == 'quarter':
            current_quarter = (today.month - 1) // 3 + 1
            start_date = datetime(today.year, 3 * current_quarter - 2, 1).date()
            end_date = today
        elif period == 'year':
            start_date = today.replace(month=1, day=1)
            end_date = today
        else:
            # Default to this month
            start_date = today.replace(day=1)
            end_date = today
        
        # Build SQL query for cleared transactions
        query = """
            SELECT 
                dst.id,
                dst.invoice_number,
                dst.date,
                dst.due_date,
                dst.transaction_type,
                dst.quantity,
                dst.unit_price,
                dst.total_amount,
                dst.discount,
                dst.tax,
                dst.advance,
                dst.description,
                dst.created_at,
                
                -- Customer info
                up.id as customer_id,
                COALESCE(u.first_name || ' ' || u.last_name, up.display_name, 'Unknown') as customer_name,
                up.phone as customer_phone,
                u.email as customer_email,
                
                -- Item info
                il.product_name as item_name,
                il.code as item_code,
                
                -- Container info
                c.name as container_name,
                c.identifier as container_id,
                
                -- Payment info
                COALESCE(SUM(p.amount), 0) as paid_amount,
                COUNT(p.id) as payment_count,
                MAX(p.date) as last_payment_date,
                MAX(p.method) as last_payment_method,
                
                -- Settlement info
                (MAX(p.date) - dst.date) as days_to_settle,
                CASE 
                    WHEN COUNT(p.id) = 1 THEN 'full'
                    WHEN COUNT(p.id) > 1 THEN 'partial'
                    ELSE 'unknown'
                END as settlement_type
                
            FROM daily_sale_dailysaletransaction dst
            LEFT JOIN accounts_userprofile up ON dst.customer_id = up.id
            LEFT JOIN auth_user u ON up.user_id = u.id
            LEFT JOIN containers_inventory_list il ON dst.item_id = il.id
            LEFT JOIN containers_container c ON dst.container_id = c.id
            LEFT JOIN daily_sale_payment p ON dst.id = p.transaction_id
            
            WHERE dst.date BETWEEN %s AND %s
            AND dst.balance = 0
            AND dst.total_amount > 0
            
        """
        
        params = [start_date, end_date]
        
        # Add filters
        if customer_id:
            query += " AND dst.customer_id = %s"
            params.append(customer_id)
        
        if payment_method:
            query += " AND p.method = %s"
            params.append(payment_method)
        
        if settlement_type:
            if settlement_type == 'full':
                query += " AND COUNT(p.id) = 1"
            elif settlement_type == 'partial':
                query += " AND COUNT(p.id) > 1"
            elif settlement_type == 'advance':
                query += " AND dst.advance > 0"
        
        query += """
            GROUP BY dst.id, up.id, u.id, il.id, c.id
            HAVING COALESCE(SUM(p.amount), 0) >= dst.total_amount
        """
        
        # Add sorting
        if sort_by == 'date_desc':
            query += " ORDER BY dst.date DESC, dst.created_at DESC"
        elif sort_by == 'date_asc':
            query += " ORDER BY dst.date ASC, dst.created_at ASC"
        elif sort_by == 'amount_desc':
            query += " ORDER BY dst.total_amount DESC"
        elif sort_by == 'amount_asc':
            query += " ORDER BY dst.total_amount ASC"
        elif sort_by == 'settlement_desc':
            query += " ORDER BY days_to_settle DESC"
        
        # Execute query
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description]
            transactions = []
            
            for row in cursor.fetchall():
                transaction = dict(zip(columns, row))
                
                # Convert decimals
                for key in ['total_amount', 'discount', 'tax', 'advance', 'paid_amount', 'unit_price']:
                    if transaction[key] is not None:
                        transaction[key] = Decimal(str(transaction[key]))
                
                # Format dates
                if transaction['date']:
                    transaction['date'] = transaction['date'].strftime('%Y-%m-%d')
                
                if transaction['last_payment_date']:
                    transaction['settlement_date'] = transaction['last_payment_date'].strftime('%Y-%m-%d')
                    transaction['is_recent'] = (today - transaction['last_payment_date']).days <= 1
                
                # Customer initials
                if transaction['customer_name']:
                    words = transaction['customer_name'].split()
                    transaction['customer_initials'] = ''.join([w[0] for w in words[:2]]).upper()
                
                transactions.append(transaction)
        
        # Calculate statistics
        total_amount = sum(t['total_amount'] for t in transactions)
        avg_settlement_days = sum(t.get('days_to_settle', 0) or 0 for t in transactions) / len(transactions) if transactions else 0
        
        # Get top customer
        customer_totals = {}
        for t in transactions:
            customer_id = t['customer_id']
            if customer_id:
                customer_totals[customer_id] = customer_totals.get(customer_id, 0) + float(t['total_amount'])
        
        top_customer = max(customer_totals.items(), key=lambda x: x[1], default=(None, 0))
        
        cleared_stats = {
            'total_amount': total_amount,
            'transaction_count': len(transactions),
            'avg_settlement_days': avg_settlement_days,
            'top_customer': {
                'id': top_customer[0],
                'name': next((t['customer_name'] for t in transactions if t['customer_id'] == top_customer[0]), 'N/A'),
                'amount': top_customer[1],
                'count': sum(1 for t in transactions if t['customer_id'] == top_customer[0]),
            },
            'quick_settlements': sum(1 for t in transactions if (t.get('days_to_settle', 999) or 999) < 7),
            'immediate_settlements': sum(1 for t in transactions if (t.get('days_to_settle', 999) or 999) == 0),
        }
        
        # Pagination
        paginator = Paginator(transactions, 20)
        page_number = request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        
        # Get customer list for filter
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT up.id, 
                       COALESCE(u.first_name || ' ' || u.last_name, up.display_name, 'Unknown') as name
                FROM daily_sale_dailysaletransaction dst
                LEFT JOIN accounts_userprofile up ON dst.customer_id = up.id
                LEFT JOIN auth_user u ON up.user_id = u.id
                WHERE dst.balance = 0
                ORDER BY name
            """)
            customers = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
        
        context = {
            'page_obj': page_obj,
            'paginator': paginator,
            'cleared_transactions': page_obj.object_list,
            'cleared_stats': cleared_stats,
            'customers': customers,
            'start_date': start_date,
            'end_date': end_date,
            'period': period,
            'today': today,
        }
        return render(request, "daily_sale/cleared_transactions.html", context)
        
    except Exception as e:
        print(f"Cleared transactions error: {e}")
        return render(request, "daily_sale/cleared_transactions.html", {
            'error': True,
            'error_message': 'Error loading cleared transactions'
        })        


@require_GET
@login_required
def ajax_search_containers(request):
    q = (request.GET.get("q") or "").strip()
    limit = int(request.GET.get("limit") or 25)
    from containers.models import Container
    qs = Container.objects.all()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(identifier__icontains=q))
    results = [{"id": c.pk, "text": getattr(c, "name", str(c))} for c in qs.order_by("name")[:limit]]
    return JsonResponse({"results": results})

@require_GET
@login_required
def ajax_search_items(request):
    q = (request.GET.get("q") or "").strip()
    limit = int(request.GET.get("limit") or 25)
    from containers.models import Inventory_List
    qs = Inventory_List.objects.all()
    if q:
        qs = qs.filter(Q(product_name__icontains=q) | Q(model__icontains=q))
    results = [{"id": i.pk, "text": getattr(i, "product_name", str(i))} for i in qs.order_by("product_name")[:limit]]
    return JsonResponse({"results": results})

@require_GET
@login_required
def ajax_search_companies(request):
    q = (request.GET.get("q") or "").strip()
    limit = int(request.GET.get("limit") or 25)
    from accounts.models import Company
    qs = Company.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)
    results = [{"id": c.pk, "text": getattr(c, "name", str(c))} for c in qs.order_by("name")[:limit]]
    return JsonResponse({"results": results})

@require_GET
@login_required
def ajax_search_customers(request):
    q = (request.GET.get("q") or "").strip()
    limit = int(request.GET.get("limit") or 25)
    from accounts.models import UserProfile
    qs = UserProfile.objects.select_related("user").all()
    if q:
        qs = qs.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(user__email__icontains=q) | Q(phone__icontains=q))
    results = []
    for u in qs.order_by("user__first_name")[:limit]:
        text = getattr(u, "display_name", None) or (u.user.get_full_name() if getattr(u, "user", None) else str(u))
        results.append({"id": u.pk, "text": text})
    return JsonResponse({"results": results})
