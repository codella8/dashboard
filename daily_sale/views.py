# daily_sale/views.py
from decimal import Decimal
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET
from django.db import transaction as db_transaction
from django.contrib import messages
from django.db import transaction
from django.template.loader import get_template, render_to_string
from django.contrib.auth.decorators import login_required
from xhtml2pdf import pisa
from io import BytesIO
import qrcode
from uuid import UUID
import base64
from containers .models import Container
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.utils import timezone
from decimal import Decimal,ROUND_HALF_UP
from django.db.models import Sum, Q, F, Count, Avg
from django.db import connection
import json
from datetime import datetime, timedelta, date
from django.db.models.functions import Coalesce
from django.db.models import DecimalField
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import csv
from django.utils.encoding import smart_str
from .models import DailySaleTransaction, Payment, DailySummary, DailySaleTransactionItem
from .forms import DailySaleTransactionForm, PaymentForm
from .report import get_sales_summary, sales_timeseries, parse_date_param
from accounts.models import Company, UserProfile
from containers.models import Inventory_List
from .utils import recompute_daily_summary_for_date, recompute_outstanding_for_customer,get_customer_outstanding_summary

logger = logging.getLogger(__name__)

TAX_RATE = Decimal('0.10')

@login_required
def customer_detail(request, customer_id=None):
    if customer_id:
        if not request.user.is_staff:
            messages.error(request, "you do not have access to this page!")
            return redirect('accounts:home')
        customer = get_object_or_404(UserProfile, id=customer_id, role=UserProfile.ROLE_CUSTOMER)
        is_self_view = False
    else:
        if request.user.is_staff:
            messages.info(request, "check from admin dashboard!")
            return redirect('accounts:dashboard')
        try:
            customer = UserProfile.objects.get(user=request.user, role=UserProfile.ROLE_CUSTOMER)
            is_self_view = True
        except UserProfile.DoesNotExist:
            messages.error(request, "Customer Profile Not Found For You!")
            return redirect('accounts:home')

    if request.method == "POST" and request.user.is_staff:
        payment_form = PaymentForm(request.POST)
        if payment_form.is_valid():
            payment = payment_form.save(commit=False)
            tx_id = request.POST.get("transaction_id")
            if tx_id:
                payment.transaction = get_object_or_404(DailySaleTransaction, id=tx_id)
                payment.save()
                recompute_outstanding_for_customer(customer.id)
                messages.success(request, "Payment recorded successfully.")
                return redirect(reverse("daily_sale:customer_detail", kwargs={"customer_id": customer.id}))
        else:
            messages.error(request, "Payment form is invalid!")
    else:
        payment_form = PaymentForm()

    recompute_outstanding_for_customer(customer.id)
    outstanding = get_customer_outstanding_summary(customer.id)
    total_debt = outstanding.get('total_debt', Decimal('0.00'))
    transactions_count = outstanding.get('transactions_count', 0)
    last_transaction = outstanding.get('last_transaction')
    transactions = DailySaleTransaction.objects.filter(customer=customer).select_related('item').order_by('-date')
    tx_data = []
    for tx in transactions:
        paid_amount = Payment.objects.filter(transaction=tx).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        remaining_amount = (tx.total_amount or Decimal('0.00')) - paid_amount

        tax_amount = (tx.total_amount or Decimal('0.00')) * Decimal(tx.tax_rate if hasattr(tx, 'tax_rate') else 0)
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

    total_sales = sum(tx['total_amount'] or Decimal('0.00') for tx in tx_data)
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
        'tax_rate': (getattr(transactions.first(), 'tax_rate', 0) * 100) if transactions else 0,
        'is_self_view': is_self_view,
        'is_admin': request.user.is_staff,
        'payment_form': payment_form,
    }
    return render(request, 'daily_sale/customer_detail.html', context)

@login_required
@db_transaction.atomic
def transaction_create(request):
    """ایجاد تراکنش جدید (نسخه اصلی با لاگ‌گیری بهتر)"""
    if request.method == "POST":
        logger.info("=" * 50)
        logger.info("🔄 Transaction creation started")
        
        form = DailySaleTransactionForm(request.POST)

        if form.is_valid():
            try:
                transaction = form.save(commit=False)
                transaction.created_by = request.user
                transaction.subtotal = Decimal(request.POST.get("subtotal", "0"))
                transaction.tax_amount = Decimal(request.POST.get("tax_amount", "0"))
                transaction.total_amount = Decimal(request.POST.get("total_amount", "0"))
                transaction.balance = Decimal(request.POST.get("balance", "0"))
                transaction.advance = Decimal(request.POST.get("advance", "0") or "0")

                # وضعیت پرداخت
                if transaction.advance >= transaction.total_amount and transaction.total_amount > Decimal("0"):
                    transaction.payment_status = "paid"
                    transaction.balance = Decimal("0")
                elif transaction.advance > Decimal("0"):
                    transaction.payment_status = "partial"
                    transaction.balance = transaction.total_amount - transaction.advance
                else:
                    transaction.payment_status = "unpaid"
                    transaction.balance = transaction.total_amount
                
                transaction.save()
                logger.info(f"✅ Transaction created: {transaction.id}")
                
                # ایجاد پرداخت اولیه اگر وجود دارد
                if transaction.advance > Decimal("0"):
                    Payment.objects.create(
                        transaction=transaction,
                        amount=transaction.advance,
                        method=request.POST.get("payment_method", "cash"),
                        date=transaction.date,
                        created_by=request.user,
                        note=f"Initial payment for invoice {transaction.invoice_number or 'N/A'}"
                    )
                    logger.info(f"💰 Initial payment created: {transaction.advance}")
                
                # ایجاد آیتم‌های تراکنش
                items_json = request.POST.get("items_data", "[]")
                items_created = 0
                
                try:
                    items_list = json.loads(items_json)
                    logger.info(f"📦 Processing {len(items_list)} items")
                except json.JSONDecodeError as e:
                    logger.error(f"❌ JSON decode error: {e}")
                    messages.error(request, "Invalid items data format.")
                    transaction.delete()
                    return render(request, "daily_sale/transaction_create.html", {"form": form})
                
                for item_data in items_list:
                    raw_item_id = item_data.get("item_id")
                    if not raw_item_id:
                        continue
                    
                    try:
                        inventory = Inventory_List.objects.get(pk=raw_item_id)
                        quantity = Decimal(str(item_data.get("quantity", 1)))
                        unit_price = Decimal(str(item_data.get("unit_price", 0)))
                        discount = Decimal(str(item_data.get("discount", 0)))
                        subtotal = (quantity * unit_price).quantize(Decimal("0.01"))
                        taxable = (subtotal - discount).quantize(Decimal("0.01"))
                        if taxable < Decimal("0"):
                            taxable = Decimal("0")

                        tax_amount = (taxable * transaction.tax / Decimal("100")).quantize(
                            Decimal("0.01")
                        )
                        total = (taxable + tax_amount).quantize(Decimal("0.01"))
                        container_obj = inventory.container if inventory.container else None
                        
                        DailySaleTransactionItem.objects.create(
                            transaction=transaction,
                            item=inventory,
                            container=container_obj,
                            quantity=quantity,
                            unit_price=unit_price,
                            discount=discount,
                            subtotal=subtotal,
                            tax_amount=tax_amount,
                            total_amount=total,
                        )
                        items_created += 1
                        
                    except Exception as e:
                        logger.error(f"❌ Error saving item: {str(e)}")
                        continue
                
                if items_created == 0:
                    logger.error("❌ No items created, rolling back transaction")
                    messages.error(request, "No valid item found.")
                    transaction.delete()
                    return render(request, "daily_sale/transaction_create.html", {"form": form})
                
                logger.info(f"✅ {items_created} items created successfully")
                
                # ایجاد شماره فاکتور
                if not transaction.invoice_number:
                    date_str = datetime.now().strftime('%Y%m%d')
                    prefix = "INV"

                    last_inv = DailySaleTransaction.objects.filter(
                        invoice_number__startswith=f"{prefix}-{date_str}-"
                    ).order_by('-invoice_number').first()

                    if last_inv:
                        try:
                            last_num = int(last_inv.invoice_number.split('-')[-1])
                            new_num = last_num + 1
                        except ValueError:
                            new_num = 1
                    else:
                        new_num = 1

                    transaction.invoice_number = f"{prefix}-{date_str}-{new_num:04d}"
                    transaction.save(update_fields=["invoice_number"])
                    logger.info(f"🏷️ Invoice number assigned: {transaction.invoice_number}")
                
                # 🔥 **اینجا مهم‌ترین بخش: بازمحاسبه خلاصه روزانه**
                logger.info(f"📊 Recomputing daily summary for date: {transaction.date}")
                summary = recompute_daily_summary_for_date(transaction.date)
                
                if summary:
                    logger.info(f"✅ Daily summary updated for {transaction.date}")
                    logger.info(f"   Sales: {summary.total_sales}, Profit: {summary.total_profit}")
                    logger.info(f"   Transactions: {summary.transactions_count}, Items: {summary.items_sold}")
                else:
                    logger.warning(f"⚠️ Could not compute daily summary for {transaction.date}")
                
                # بازمحاسبه وضعیت مشتری
                if transaction.customer:
                    logger.info(f"👤 Recomputing customer outstanding: {transaction.customer.id}")
                    try:
                        recompute_outstanding_for_customer(transaction.customer.id)
                    except Exception as e:
                        logger.error(f"❌ Error in customer recompute: {e}")
                
                messages.success(
                    request,
                    f"✅ تراکنش #{transaction.invoice_number} با موفقیت ایجاد شد ({items_created} قلم کالا)"
                )
                
                logger.info("=" * 50)
                logger.info(f"🎉 Transaction #{transaction.invoice_number} completed successfully")
                
                return redirect("daily_sale:invoice", pk=transaction.pk)

            except Exception as e:
                logger.error(f"❌ Error in transaction creation: {str(e)}", exc_info=True)
                messages.error(request, f"خطا در ایجاد تراکنش: {str(e)}")
                return render(request, "daily_sale/transaction_create.html", {"form": form})
        
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
            logger.warning("❌ Form validation failed")
    
    # GET Request
    form = DailySaleTransactionForm(initial={
        "date": timezone.now().date(),
        "tax": Decimal("5.00"),
        "due_date": timezone.now().date() + timezone.timedelta(days=30),
    })
    
    logger.info("📄 Loading transaction create form")
    return render(request, "daily_sale/transaction_create.html", {"form": form})

@login_required
@require_GET
def calculate_tax_preview(request):
    """API endpoint for real-time tax calculation preview with paid amount"""
    try:
        quantity = Decimal(request.GET.get('quantity', 1))
        unit_price = Decimal(request.GET.get('unit_price', 0))
        discount = Decimal(request.GET.get('discount', 0))
        tax_percent = Decimal(request.GET.get('tax', 5))
        paid_amount = Decimal(request.GET.get('paid_amount', 0)) 
        subtotal = (quantity * unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        taxable_amount = (subtotal - discount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if taxable_amount < Decimal('0'):
            taxable_amount = Decimal('0')
        tax_amount = (taxable_amount * (tax_percent / Decimal('100'))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        
        total_amount = (taxable_amount + tax_amount).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        balance = (total_amount - paid_amount).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        if paid_amount >= total_amount and total_amount > 0:
            payment_status = 'paid'
            payment_status_display = 'paid'
            payment_class = 'success'
        elif paid_amount > 0:
            payment_status = 'partial'
            payment_status_display = 'partial'
            payment_class = 'warning'
        else:
            payment_status = 'unpaid'
            payment_status_display = 'unpaid'
            payment_class = 'danger'
        
        payment_percentage = (paid_amount / total_amount * 100) if total_amount > 0 else 0
        
        return JsonResponse({
            'success': True,
            'subtotal': str(subtotal),
            'taxable_amount': str(taxable_amount),
            'tax_amount': str(tax_amount),
            'total_amount': str(total_amount),
            'balance': str(balance),
            'paid_amount': str(paid_amount),
            'payment_status': payment_status,
            'payment_status_display': payment_status_display,
            'payment_class': payment_class,
            'payment_percentage': round(payment_percentage, 2),
            'calculation_details': {
                'subtotal_formula': f"{quantity} × {unit_price} = {subtotal}",
                'taxable_formula': f"{subtotal} - {discount} = {taxable_amount}",
                'tax_formula': f"{taxable_amount} × ({tax_percent}%) = {tax_amount}",
                'total_formula': f"{taxable_amount} + {tax_amount} = {total_amount}",
                'balance_formula': f"{total_amount} - {paid_amount} = {balance}",
                'payment_percentage_formula': f"({paid_amount} ÷ {total_amount}) × 100 = {payment_percentage:.2f}%",
            }
        })
        
    except Exception as e:
        logger.error(f"Error in calculate_tax_preview: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
        
def transaction_edit(request, pk):
    obj = get_object_or_404(DailySaleTransaction, pk=pk)
    if request.method == "POST":
        form = DailySaleTransactionForm(request.POST, instance=obj, user=request.user)
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
    try:
        start_date = parse_date_param(request.GET.get("start_date"))
        end_date = parse_date_param(request.GET.get("end_date"))
        transaction_type = request.GET.get("type", "")
        customer_id = request.GET.get("customer", "")
        company_id = request.GET.get("company", "")
        invoice_number = request.GET.get("invoice", "").strip()
        status_filter = request.GET.get("status", "")
        items_per_page = int(request.GET.get("per_page", 25))
        export_csv = request.GET.get("export") == "csv"
        
        qs = DailySaleTransaction.objects.select_related(
            "item", 
            "customer__user", 
            "company", 
            "container"
        ).order_by("-date", "-created_at")
        
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
        
        total_count = qs.count()

        stats = {}

        sales_total = qs.filter(transaction_type='sale').aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        stats['total_sales'] = sales_total
        
        purchases_total = qs.filter(transaction_type='purchase').aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        stats['total_purchases'] = purchases_total
        
        returns_total = qs.filter(transaction_type='return').aggregate(
            total=Coalesce(Sum('total_amount'), Decimal('0'), output_field=DecimalField())
        )['total']
        stats['total_returns'] = returns_total
        outstanding_total = Decimal('0')
        outstanding_count = 0

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
        items_sold = qs.filter(transaction_type='sale').aggregate(
            total=Coalesce(Sum('quantity'), 0)
        )['total']
        stats['items_sold'] = items_sold

        if total_count > 0:
            avg_transaction = (sales_total + purchases_total + returns_total) / total_count
        else:
            avg_transaction = Decimal('0')
        stats['avg_transaction'] = avg_transaction

        if export_csv:
            return export_transactions_to_csv(qs)
        
        paginator = Paginator(qs, items_per_page)
        page_number = request.GET.get("page", 1)
        
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        transactions_with_payments = []
        for transaction in page_obj:
            paid_amount = Payment.objects.filter(transaction=transaction).aggregate(
                total=Coalesce(Sum('amount'), Decimal('0'), output_field=DecimalField())
            )['total'] or Decimal('0')
            
            remaining = transaction.total_amount - paid_amount
            if paid_amount == Decimal('0'):
                payment_status = 'unpaid'
                status_class = 'danger'
            elif remaining == Decimal('0'):
                payment_status = 'paid'
                status_class = 'success'
            else:
                payment_status = 'partial'
                status_class = 'warning'
                 
            transaction.paid_amount = paid_amount
            transaction.remaining_balance = remaining
            transaction.payment_status = payment_status
            transaction.status_class = status_class
            transaction.payment_percentage = int((paid_amount / transaction.total_amount * 100)) if transaction.total_amount > 0 else 0
            transactions_with_payments.append(transaction)

        customers = UserProfile.objects.filter(
            daily_transactions__isnull=False
        ).distinct().order_by('user__first_name')[:50]
        
        companies = Company.objects.filter(
            daily_transactions__isnull=False
        ).distinct().order_by('name')[:50]

        start_date_str = start_date.strftime("%Y-%m-%d") if start_date else ""
        end_date_str = end_date.strftime("%Y-%m-%d") if end_date else ""
        
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
        
        try:
            qs = DailySaleTransaction.objects.select_related(
                "item", "customer__user", "company", "container"
            ).order_by("-date", "-created_at")[:100]
            
            paginator = Paginator(qs, 25)
            page_obj = paginator.page(1)
            
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
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="transactions_export.csv"'
    writer = csv.writer(response)
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

def calculate_daily_series_from_transactions(start_date, end_date):
    try:
        daily_series = []
        date_range = [
            start_date + timedelta(days=x) 
            for x in range((end_date - start_date).days + 1)
        ]
        
        for current_date in date_range:
            # تراکنش‌های روز
            transactions = DailySaleTransaction.objects.filter(date=current_date)
            
            if transactions.exists():
                # محاسبات روز
                day_stats = transactions.aggregate(
                    total_sales=Sum('total_amount', filter=Q(transaction_type='sale')),
                    total_purchases=Sum('total_amount', filter=Q(transaction_type='purchase')),
                    items_sold=Sum('items__quantity', filter=Q(transaction_type='sale')),
                    transactions_count=Count('id'),
                    customers_count=Count('customer', distinct=True),
                )
                
                # پرداخت‌های روز
                payments = Payment.objects.filter(date=current_date)
                total_paid = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
                
                day_data = {
                    'date': current_date,
                    'total_sales': day_stats.get('total_sales') or Decimal('0'),
                    'total_purchases': day_stats.get('total_purchases') or Decimal('0'),
                    'net_profit': (day_stats.get('total_sales') or Decimal('0')) - 
                                 (day_stats.get('total_purchases') or Decimal('0')),
                    'transactions_count': day_stats.get('transactions_count') or 0,
                    'items_sold': day_stats.get('items_sold') or 0,
                    'customers_count': day_stats.get('customers_count') or 0,
                    'cash_in': total_paid,
                    'cash_out': day_stats.get('total_purchases') or Decimal('0'),
                    'from_cache': False,
                }
                
                daily_series.append(day_data)
        
        return daily_series
        
    except Exception as e:
        logger.error(f"Error in calculate_daily_series_from_transactions: {e}")
        return []


def calculate_sales_trend(daily_series):
    """محاسبه روند فروش"""
    if len(daily_series) < 2:
        return {'trend': 'stable', 'percentage': 0}
    
    try:
        # مرتب‌سازی بر اساس تاریخ
        sorted_series = sorted(daily_series, key=lambda x: x['date'])
        
        # میانگین 7 روز اول
        first_week = sorted_series[:7] if len(sorted_series) >= 7 else sorted_series[:len(sorted_series)//2]
        first_avg = sum([day['total_sales'] for day in first_week]) / len(first_week)
        
        # میانگین 7 روز آخر
        last_week = sorted_series[-7:] if len(sorted_series) >= 7 else sorted_series[len(sorted_series)//2:]
        last_avg = sum([day['total_sales'] for day in last_week]) / len(last_week)
        
        if first_avg == 0:
            return {'trend': 'up', 'percentage': 100}
        
        percentage_change = ((last_avg - first_avg) / first_avg) * 100
        
        if percentage_change > 10:
            return {'trend': 'up', 'percentage': round(percentage_change, 1)}
        elif percentage_change < -10:
            return {'trend': 'down', 'percentage': round(abs(percentage_change), 1)}
        else:
            return {'trend': 'stable', 'percentage': round(abs(percentage_change), 1)}
            
    except Exception as e:
        logger.error(f"Error calculating trend: {e}")
        return {'trend': 'stable', 'percentage': 0}

@login_required
def daily_summary(request):
    try:
        start_date_str = request.GET.get("start_date")
        end_date_str = request.GET.get("end_date")
        today = timezone.now().date()
        default_end_date = today
        default_start_date = today - timedelta(days=30)
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
        if start_date > end_date:
            start_date, end_date = end_date, start_date
        
        if (end_date - start_date).days > 365:
            start_date = end_date - timedelta(days=365)
        
        transactions = DailySaleTransaction.objects.filter(date__range=[start_date, end_date]).select_related('customer', 'company', 'item')
        period_stats = transactions.aggregate(
            total_sales=Sum('total_amount', filter=Q(transaction_type='sale')),
            total_purchases=Sum('total_amount', filter=Q(transaction_type='purchase')),
            total_returns=Sum('total_amount', filter=Q(transaction_type='return')),
            total_transactions=Count('id'),
            total_quantity=Sum('quantity', filter=Q(transaction_type='sale')),
            avg_transaction=Avg('total_amount'),
        )

        cash_in_data = Payment.objects.filter(date__range=[start_date, end_date]).aggregate(total=Sum('amount'), count=Count('id'))
        cash_in_total = cash_in_data['total'] or 0
        cash_out_data = DailySaleTransaction.objects.filter(date__range=[start_date, end_date], transaction_type__in=['purchase', 'return']).aggregate(total=Sum('total_amount'), count=Count('id'))
        cash_out_total = cash_out_data['total'] or 0
        cash_out_count = cash_out_data['count'] or 0
        net_profit = cash_in_total - cash_out_total
        payment_stats = {
            'fully_paid': transactions.filter(payment_status='paid').count(),
            'partially_paid': transactions.filter(payment_status='partial').count(),
            'unpaid': transactions.filter(payment_status='unpaid').count(),
            'total_transactions': transactions.count(),
            'total_collected': cash_in_total,
            'total_outstanding': transactions.filter(Q(payment_status='unpaid') | Q(payment_status='partial')).aggregate(total=Sum('balance'))['total'] or 0,
        }

        if payment_stats['total_transactions'] > 0:
            payment_stats['fully_paid_percentage'] = (payment_stats['fully_paid'] / payment_stats['total_transactions'] * 100)
            payment_stats['partially_paid_percentage'] = (payment_stats['partially_paid'] / payment_stats['total_transactions'] * 100)
            payment_stats['unpaid_percentage'] = (payment_stats['unpaid'] / payment_stats['total_transactions'] * 100)
        else:
            payment_stats['fully_paid_percentage'] = 0
            payment_stats['partially_paid_percentage'] = 0
            payment_stats['unpaid_percentage'] = 0

        collection_rate = (payment_stats['total_collected'] / period_stats['total_sales'] * 100) if period_stats['total_sales'] > 0 else 0
        daily_series = []
        date_range = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        for current_date in date_range:
            day_transactions = transactions.filter(date=current_date)
            day_sales = day_transactions.filter(transaction_type='sale').aggregate(total=Sum('total_amount'))['total'] or 0
            day_cash_in = Payment.objects.filter(date=current_date).aggregate(total=Sum('amount'))['total'] or 0
            day_cash_out = day_transactions.filter(transaction_type__in=['purchase', 'return']).aggregate(total=Sum('total_amount'))['total'] or 0

            day_data = {
                'date': current_date,
                'total_sales': day_sales,
                'cash_in': day_cash_in,
                'cash_out': day_cash_out,
                'profit': day_cash_in - day_cash_out,
                'transactions_count': day_transactions.count(),
            }
            daily_series.append(day_data)
        context = {
            'start_date': start_date,
            'end_date': end_date,
            'period_summary': period_stats,
            'daily_series': daily_series,
            'payment_stats': payment_stats,
            'cash_in_total': cash_in_total,
            'cash_out_total': cash_out_total,
            'collection_rate': collection_rate,
        }

        return render(request, "daily_sale/daily_summary.html", context)

    except Exception as e:
        logger.error(f"Error in daily_summary: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'error'}, status=500)
        
    except Exception as e:
        logger.error(f"Error in daily_summary: {str(e)}", exc_info=True)
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
                'customers_count': 0,
            },
            'daily_series': [],
            'cash_in_total': Decimal('0.00'),
            'cash_out_total': Decimal('0.00'),
            'payment_stats': {
                'fully_paid': 0,
                'partially_paid': 0,
                'unpaid': 0,
                'total_collected': Decimal('0.00'),
                'total_outstanding': Decimal('0.00'),
                'collection_rate': 0,
                'avg_outstanding': Decimal('0.00'),
                'fully_paid_percentage': 0,
                'partially_paid_percentage': 0,
                'unpaid_percentage': 0,
            },
            'error': True,
            'error_message': f'Error In Loading Data!: {str(e)}',
        }
        return render(request, "daily_sale/daily_summary.html", context)
    
@login_required
@require_GET
def generate_daily_report(request):
    try:
        start_date_str = request.GET.get("start_date")
        end_date_str = request.GET.get("end_date")
        
        if not start_date_str or not end_date_str:
            raise ValueError("start, and end date is nesseccery!")
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        period_stats = DailySaleTransaction.objects.filter(
            date__range=[start_date, end_date]
        ).aggregate(
            total_sales=Sum('total_amount'),
            total_purchases=Sum('total_amount', filter=Q(transaction_type='purchase')),
            total_profit=Sum('total_amount', filter=Q(transaction_type='sale')),
            total_transactions=Count('id')
        )
        cash_in_total = Payment.objects.filter(date__range=[start_date, end_date]).aggregate(total=Sum('amount'))['total'] or 0
        cash_out_total = DailySaleTransaction.objects.filter(
            date__range=[start_date, end_date], transaction_type__in=['purchase', 'return']
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        report_data = {
            'start_date': start_date_str,
            'end_date': end_date_str,
            'total_sales': float(period_stats['total_sales'] or 0),
            'total_purchases': float(period_stats['total_purchases'] or 0),
            'net_profit': float(period_stats['total_profit'] or 0),
            'cash_in_total': float(cash_in_total),
            'cash_out_total': float(cash_out_total),
        }
        return HttpResponse(
            json.dumps(report_data, indent=2, ensure_ascii=False),
            content_type='application/json'
        )
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def get_real_time_daily_summary(request, start_date, end_date, today):
    try:

        period_summary = get_sales_summary(start_date, end_date)
        daily_timeseries = sales_timeseries(start_date, end_date, group_by="day")
    
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
        chart_labels = []
        chart_sales = []
        for day in daily_timeseries:
            chart_labels.append(day['date'].strftime('%b %d'))
            chart_sales.append(float(day['total_sales']))
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
    ویوی ساده برای نمایش مشتریان بدهکار با جزئیات محصولات
    """
    try:
        # دریافت پارامترهای فیلتر
        search_query = request.GET.get('search', '')
        
        # لیست مشتریان
        customers = UserProfile.objects.filter(
            role=UserProfile.ROLE_CUSTOMER
        ).select_related('user')
        
        outstanding_customers = []
        
        for customer in customers:
            # محاسبه بدهی کل مشتری
            customer_data = calculate_customer_debt(customer)
            
            if customer_data and customer_data['total_debt'] > 0:
                # دریافت جزئیات تراکنش‌های بدهکار
                transactions_data = get_customer_debt_details(customer)
                
                customer_info = {
                    'customer_id': str(customer.id),
                    'customer_name': customer.user.get_full_name() if customer.user else customer.display_name or f"مشتری {customer.id}",
                    'customer_phone': getattr(customer, 'phone', ''),
                    'customer_email': customer.user.email if customer.user else '',
                    
                    # اطلاعات مالی کلی
                    'total_debt': customer_data['total_debt'],
                    'total_paid': customer_data['total_paid'],
                    'remaining_balance': customer_data['remaining_balance'],
                    
                    # جزئیات تراکنش‌ها
                    'transactions': transactions_data,
                    
                    # تعداد تراکنش‌های بدهکار
                    'debt_transactions_count': len(transactions_data),
                    
                    # مجموع مبالغ محصولات
                    'products_total': sum(t['product_amount'] for t in transactions_data),
                }
                
                outstanding_customers.append(customer_info)
        
        # اعمال جستجو
        if search_query:
            search_lower = search_query.lower()
            outstanding_customers = [
                c for c in outstanding_customers
                if (search_lower in c['customer_name'].lower() or
                    (c['customer_phone'] and search_lower in c['customer_phone']) or
                    (c['customer_email'] and search_lower in c['customer_email'].lower()))
            ]
        
        # مرتب‌سازی بر اساس بدهی (بیشترین بدهی اول)
        outstanding_customers.sort(key=lambda x: x['total_debt'], reverse=True)
        
        # محاسبه مجموع کل
        total_summary = {
            'total_debt': sum(c['total_debt'] for c in outstanding_customers),
            'total_paid': sum(c['total_paid'] for c in outstanding_customers),
            'total_customers': len(outstanding_customers),
            'total_transactions': sum(c['debt_transactions_count'] for c in outstanding_customers),
        }
        
        context = {
            'outstanding_customers': outstanding_customers,
            'total_summary': total_summary,
            'search_query': search_query,
            'customers_count': len(outstanding_customers),
        }
        
        return render(request, 'daily_sale/old_transactions.html', context)
        
    except Exception as e:
        logger.error(f"خطا در نمایش مشتریان بدهکار: {str(e)}", exc_info=True)
        
        context = {
            'error': True,
            'error_message': f'خطا در بارگذاری داده‌ها: {str(e)}',
            'outstanding_customers': [],
            'customers_count': 0,
        }
        
        return render(request, 'daily_sale/old_transactions.html', context)


def calculate_customer_debt(customer):
    """
    محاسبه بدهی کل یک مشتری
    """
    try:
        # دریافت تمام تراکنش‌های مشتری
        transactions = DailySaleTransaction.objects.filter(customer=customer)
        
        if not transactions.exists():
            return None
        
        # محاسبه مجموع مبالغ
        total_amount = transactions.aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
        total_discount = transactions.aggregate(total=Sum('discount'))['total'] or Decimal('0')
        
        # محاسبه مجموع پرداخت‌ها
        total_payments = Payment.objects.filter(
            transaction__customer=customer
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        
        # محاسبه بدهی باقی‌مانده
        remaining_balance = total_amount - total_payments - total_discount
        
        if remaining_balance <= 0:
            return None
        
        return {
            'total_debt': total_amount,
            'total_paid': total_payments,
            'total_discount': total_discount,
            'remaining_balance': remaining_balance,
        }
        
    except Exception as e:
        logger.error(f"خطا در محاسبه بدهی مشتری {customer.id}: {str(e)}")
        return None


def get_customer_debt_details(customer):
    """
    دریافت جزئیات تراکنش‌های بدهکار مشتری با اطلاعات محصول
    """
    transactions_data = []
    
    try:
        # دریافت تراکنش‌هایی که بدهی دارند
        transactions = DailySaleTransaction.objects.filter(
            customer=customer
        ).prefetch_related('items', 'payments')
        
        for transaction in transactions:
            # محاسبه مجموع پرداخت‌های این تراکنش
            transaction_payments = Payment.objects.filter(transaction=transaction)
            total_paid = transaction_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            # محاسبه بدهی این تراکنش
            transaction_debt = transaction.total_amount - total_paid - (transaction.discount or Decimal('0'))
            
            # فقط تراکنش‌های بدهکار
            if transaction_debt > 0:
                # دریافت اطلاعات محصولات
                products_info = []
                items = transaction.items.all()
                
                for item in items:
                    product_info = {
                        'product_name': item.item.product_name if item.item else "نامشخص",
                        'product_code': item.item.code if item.item else "",
                        'quantity': item.quantity,
                        'unit_price': item.unit_price,
                        'subtotal': item.quantity * item.unit_price,
                        'discount': item.discount or Decimal('0'),
                        'tax_amount': item.tax_amount or Decimal('0'),
                        'total_amount': item.total_amount or Decimal('0'),
                    }
                    products_info.append(product_info)
                
                # اطلاعات پرداخت‌ها
                payments_info = []
                for payment in transaction_payments:
                    payment_info = {
                        'amount': payment.amount,
                        'method': payment.get_method_display(),
                        'date': payment.date,
                        'note': payment.note or '',
                    }
                    payments_info.append(payment_info)
                
                transaction_info = {
                    'invoice_number': transaction.invoice_number or f"TRX-{transaction.id}",
                    'transaction_date': transaction.date,
                    'total_amount': transaction.total_amount,
                    'discount': transaction.discount or Decimal('0'),
                    'total_paid': total_paid,
                    'remaining_debt': transaction_debt,
                    'payment_status': transaction.get_payment_status_display(),
                    
                    # اطلاعات محصولات
                    'products': products_info,
                    'products_count': len(products_info),
                    'product_amount': sum(p['total_amount'] for p in products_info),
                    
                    # اطلاعات پرداخت‌ها
                    'payments': payments_info,
                    'payments_count': len(payments_info),
                    
                    # سایر اطلاعات
                    'note': transaction.note or '',
                }
                
                transactions_data.append(transaction_info)
                
    except Exception as e:
        logger.error(f"خطا در دریافت جزئیات بدهی مشتری {customer.id}: {str(e)}")
    
    return transactions_data


class SimpleJSONEncoder(json.JSONEncoder):
    """
    JSON Encoder ساده برای انواع داده‌ای خاص
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


@login_required
def cleared_customers_view(request):
    """
    نمایش لیست مشتریانی که حساب خود را کامل پرداخت کرده‌اند
    """
    try:
        # دریافت پارامترهای فیلتر
        search_query = request.GET.get('search', '')
        period = request.GET.get('period', 'month')
        sort_by = request.GET.get('sort', 'date_desc')
        
        # تاریخ امروز برای محاسبات
        today = timezone.now().date()
        
        # محاسبه بازه زمانی
        start_date, end_date = calculate_simple_date_range(period, today)
        
        # دریافت لیست مشتریان
        customers = UserProfile.objects.filter(
            role=UserProfile.ROLE_CUSTOMER
        ).select_related('user')
        
        cleared_customers = []
        total_cleared_amount = Decimal('0')
        total_transactions_count = 0
        
        for customer in customers:
            # بررسی آیا مشتری تسویه شده است
            customer_status = check_customer_clear_status(customer, start_date, end_date)
            
            if customer_status['is_cleared']:
                customer_info = {
                    'customer_id': str(customer.id),
                    'customer_name': customer.user.get_full_name() if customer.user else customer.display_name or f"Customer {customer.id}",
                    'customer_phone': getattr(customer, 'phone', ''),
                    'customer_email': customer.user.email if customer.user else '',
                    
                    # اطلاعات مالی
                    'total_cleared_amount': customer_status['total_cleared_amount'],
                    'total_transactions': customer_status['total_transactions'],
                    'last_payment_date': customer_status['last_payment_date'],
                    'first_transaction_date': customer_status['first_transaction_date'],
                    
                    # وضعیت
                    'clear_status': 'Fully Paid',
                    'clear_days': customer_status['clear_days'],
                    
                    # جزئیات تراکنش‌ها
                    'transactions': customer_status['transactions_details'],
                    
                    # برای نمایش
                    'formatted_amount': format_currency(customer_status['total_cleared_amount']),
                    'has_phone': bool(getattr(customer, 'phone', '')),
                    'has_email': bool(customer.user and customer.user.email),
                }
                
                cleared_customers.append(customer_info)
                total_cleared_amount += customer_status['total_cleared_amount']
                total_transactions_count += customer_status['total_transactions']
        
        # اعمال جستجو
        if search_query:
            search_lower = search_query.lower()
            cleared_customers = [
                c for c in cleared_customers
                if (search_lower in c['customer_name'].lower() or
                    (c['customer_phone'] and search_lower in c['customer_phone']) or
                    (c['customer_email'] and search_lower in c['customer_email'].lower()))
            ]
        
        # مرتب‌سازی
        if sort_by == 'date_desc':
            cleared_customers.sort(key=lambda x: x['last_payment_date'] or datetime.min, reverse=True)
        elif sort_by == 'date_asc':
            cleared_customers.sort(key=lambda x: x['last_payment_date'] or datetime.min)
        elif sort_by == 'amount_desc':
            cleared_customers.sort(key=lambda x: x['total_cleared_amount'], reverse=True)
        elif sort_by == 'amount_asc':
            cleared_customers.sort(key=lambda x: x['total_cleared_amount'])
        elif sort_by == 'name_asc':
            cleared_customers.sort(key=lambda x: x['customer_name'].lower())
        elif sort_by == 'name_desc':
            cleared_customers.sort(key=lambda x: x['customer_name'].lower(), reverse=True)
        
        # محاسبه آمار
        stats = {
            'total_customers': len(cleared_customers),
            'total_amount': total_cleared_amount,
            'avg_amount_per_customer': total_cleared_amount / len(cleared_customers) if cleared_customers else Decimal('0'),
            'total_transactions': total_transactions_count,
            'period_start': start_date,
            'period_end': end_date,
        }
        
        # آماده‌سازی context
        context = {
            'cleared_customers': cleared_customers,
            'stats': stats,
            'search_query': search_query,
            'period': period,
            'sort_by': sort_by,
            'start_date': start_date,
            'end_date': end_date,
            'today': today,
            'customers_count': len(cleared_customers),
            'cleared_customers_json': json.dumps(cleared_customers, cls=SimpleJSONEncoder),
        }
        
        return render(request, 'daily_sale/cleared_customers.html', context)
        
    except Exception as e:
        logger.error(f"Error in cleared_customers_view: {str(e)}", exc_info=True)
        
        context = {
            'error': True,
            'error_message': f'Error loading data: {str(e)}',
            'cleared_customers': [],
            'customers_count': 0,
            'stats': {
                'total_customers': 0,
                'total_amount': Decimal('0'),
                'total_transactions': 0,
            }
        }
        
        return render(request, 'daily_sale/cleared_customers.html', context)


def check_customer_clear_status(customer, start_date, end_date):
    """
    بررسی وضعیت تسویه مشتری
    """
    try:
        # دریافت تمام تراکنش‌های مشتری در بازه زمانی
        transactions = DailySaleTransaction.objects.filter(
            customer=customer,
            date__range=[start_date, end_date]
        )
        
        if not transactions.exists():
            return {
                'is_cleared': False,
                'total_cleared_amount': Decimal('0'),
                'total_transactions': 0,
                'last_payment_date': None,
                'first_transaction_date': None,
                'clear_days': 0,
                'transactions_details': []
            }
        
        total_cleared = Decimal('0')
        total_transactions_count = 0
        last_payment_date = None
        first_transaction_date = None
        transactions_details = []
        
        for transaction in transactions:
            # محاسبه پرداخت‌های این تراکنش
            total_paid = Payment.objects.filter(
                transaction=transaction
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            # محاسبه بدهی باقی‌مانده
            remaining = (transaction.total_amount or Decimal('0')) - total_paid - (transaction.discount or Decimal('0'))
            
            # اگر تسویه شده باشد
            if remaining <= Decimal('0') and transaction.total_amount > Decimal('0'):
                total_cleared += transaction.total_amount
                total_transactions_count += 1
                
                # تاریخ آخرین پرداخت
                last_payment = Payment.objects.filter(
                    transaction=transaction
                ).order_by('-date').first()
                
                if last_payment:
                    if not last_payment_date or last_payment.date > last_payment_date:
                        last_payment_date = last_payment.date
                
                # تاریخ اولین تراکنش
                if not first_transaction_date or transaction.date < first_transaction_date:
                    first_transaction_date = transaction.date
                
                # جزئیات تراکنش
                transaction_detail = {
                    'invoice_number': transaction.invoice_number or f"TRX-{transaction.id}",
                    'date': transaction.date,
                    'total_amount': transaction.total_amount,
                    'total_paid': total_paid,
                    'discount': transaction.discount or Decimal('0'),
                    'status': 'Paid',
                    'payment_count': Payment.objects.filter(transaction=transaction).count(),
                }
                transactions_details.append(transaction_detail)
        
        # محاسبه روزهای از آخرین پرداخت
        clear_days = 0
        if last_payment_date:
            clear_days = (timezone.now().date() - last_payment_date.date()).days
        
        return {
            'is_cleared': total_transactions_count > 0,
            'total_cleared_amount': total_cleared,
            'total_transactions': total_transactions_count,
            'last_payment_date': last_payment_date,
            'first_transaction_date': first_transaction_date,
            'clear_days': clear_days,
            'transactions_details': transactions_details,
        }
        
    except Exception as e:
        logger.error(f"Error checking clear status for customer {customer.id}: {str(e)}")
        return {
            'is_cleared': False,
            'total_cleared_amount': Decimal('0'),
            'total_transactions': 0,
            'last_payment_date': None,
            'first_transaction_date': None,
            'clear_days': 0,
            'transactions_details': []
        }


def calculate_simple_date_range(period, today):
    """
    محاسبه بازه زمانی ساده
    """
    from datetime import timedelta
    
    if period == 'today':
        return today, today
    elif period == 'week':
        return today - timedelta(days=7), today
    elif period == 'month':
        return today - timedelta(days=30), today
    elif period == 'quarter':
        return today - timedelta(days=90), today
    elif period == 'year':
        return today - timedelta(days=365), today
    else:  # 'all'
        return today - timedelta(days=365*5), today  # 5 years


def format_currency(amount):
    """
    فرمت کردن مبلغ
    """
    try:
        return f"AED {amount:,.2f}"
    except:
        return f"AED {amount}"


# ویوی برای جزئیات مشتری
@login_required
def cleared_transactions(request, customer_id):
    """
    نمایش جزئیات یک مشتری تسویه‌شده
    """
    try:
        customer = UserProfile.objects.get(id=customer_id, role=UserProfile.ROLE_CUSTOMER)
        
        # دریافت تمام تراکنش‌های تسویه‌شده مشتری
        transactions = DailySaleTransaction.objects.filter(
            customer=customer
        ).order_by('-date')
        
        cleared_transactions = []
        total_cleared = Decimal('0')
        
        for transaction in transactions:
            total_paid = Payment.objects.filter(
                transaction=transaction
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            remaining = (transaction.total_amount or Decimal('0')) - total_paid - (transaction.discount or Decimal('0'))
            
            if remaining <= Decimal('0') and transaction.total_amount > Decimal('0'):
                # اطلاعات پرداخت‌ها
                payments = Payment.objects.filter(transaction=transaction).order_by('date')
                payment_details = []
                
                for payment in payments:
                    payment_details.append({
                        'date': payment.date,
                        'amount': payment.amount,
                        'method': payment.method,
                        'reference': payment.reference or '',
                    })
                
                transaction_data = {
                    'invoice_number': transaction.invoice_number or f"TRX-{transaction.id}",
                    'date': transaction.date,
                    'total_amount': transaction.total_amount,
                    'discount': transaction.discount or Decimal('0'),
                    'total_paid': total_paid,
                    'payment_details': payment_details,
                    'payment_count': len(payment_details),
                    'description': transaction.description or '',
                    'item': transaction.item.product_name if transaction.item else 'N/A',
                }
                
                cleared_transactions.append(transaction_data)
                total_cleared += transaction.total_amount
        
        context = {
            'customer': customer,
            'customer_name': customer.user.get_full_name() if customer.user else customer.display_name,
            'customer_phone': getattr(customer, 'phone', ''),
            'customer_email': customer.user.email if customer.user else '',
            'cleared_transactions': cleared_transactions,
            'total_cleared': total_cleared,
            'transactions_count': len(cleared_transactions),
        }
        
        return render(request, 'daily_sale/cleared_transactions.html', context)
        
    except UserProfile.DoesNotExist:
        return render(request, 'daily_sale/error.html', {
            'error_message': 'Customer not found'
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

@require_GET
@login_required
def ajax_item_autofill(request):
    item_id = request.GET.get("item_id")
    
    if not item_id:
        return JsonResponse({"error": "Item ID required"}, status=400)
    try:
        item = Inventory_List.objects.select_related(
            'container', 
            'container__company'
        ).get(pk=item_id)
        container_info = None
        container_id = None
        container_name = None
        container_identifier = None
        
        if item.container:
            container_id = str(item.container.id)
            container_name = item.container.name if hasattr(item.container, 'name') else str(item.container)
            container_identifier = item.container.identifier if hasattr(item.container, 'identifier') else ""
            container_info = {
                "id": container_id,
                "text": container_name,
                "name": container_name,
                "identifier": container_identifier,
                "size": item.container.size if hasattr(item.container, 'size') else "",
                "type": item.container.type if hasattr(item.container, 'type') else "",
            }
        company_info = None
        company_id = None
        company_name = None
        
        if item.container and item.container.company:
            company_id = str(item.container.company.id)
            company_name = item.container.company.name if hasattr(item.container.company, 'name') else str(item.container.company)       
            company_info = {
                "id": company_id,
                "text": company_name,
                "name": company_name,
                "address": item.container.company.address if hasattr(item.container.company, 'address') else "",
                "phone": item.container.company.phone if hasattr(item.container.company, 'phone') else "",
                "email": item.container.company.email if hasattr(item.container.company, 'email') else "",
            }
        
        return JsonResponse({
            "success": True,
            "unit_price": float(item.unit_price) if item.unit_price else 0.0,
            "price": float(item.price) if item.price else 0.0,
            "sold_price": float(item.sold_price) if item.sold_price else 0.0,
            "available_quantity": float(item.in_stock_qty) if item.in_stock_qty else 0.0,
            "total_sold_qty": float(item.total_sold_qty) if item.total_sold_qty else 0.0,
            "total_sold_count": item.total_sold_count if item.total_sold_count else 0,
            "container": container_info,
            "container_id": container_id,
            "container_name": container_name,
            "container_identifier": container_identifier,
            "company": company_info,
            "company_id": company_id,
            "company_name": company_name,
            "product_name": item.product_name,
            "model": item.model if item.model else "",
            "description": item.description if item.description else "",
            "code": item.code if item.code else "",
            "make": item.make if item.make else "",
            "date_added": item.date_added.strftime('%Y-%m-%d') if item.date_added else "",
            "display_info": {
                "product": f"{item.code} - {item.product_name}" if item.code else item.product_name,
                "container": f"{container_name} ({container_identifier})" if container_name and container_identifier else container_name or "",
                "company": company_name or "",
                "price": f"AED {item.unit_price:,.0f}" if item.unit_price else "AED 0",
                "stock": f"{item.in_stock_qty:,.0f} in stock" if item.in_stock_qty else "Out of stock",
            }
        })
        
    except Inventory_List.DoesNotExist:
        return JsonResponse({"success": False, "error": "Item not found"}, status=404)
    except Exception as e: 
        import traceback
        logger.error(f"Error in ajax_item_autofill: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def invoice_view(request, pk):
    transaction = get_object_or_404(
        DailySaleTransaction.objects.select_related(
            'company', 
            'customer', 
            'created_by',
            'container'
        ),
        pk=pk
    )

    items = transaction.items.all().select_related(
        'item',
        'container'
    ).order_by('id')
    
    # محاسبات واقعی از دیتابیس
    subtotal = Decimal('0')
    discount_total = Decimal('0')
    tax_amount = Decimal('0')
    
    for item in items:
        # محاسبه سابتوتال از دیتابیس
        item_subtotal = item.quantity * item.unit_price
        subtotal += item_subtotal
        
        # تخفیف
        item_discount = item.discount or Decimal('0')
        discount_total += item_discount
        
        # مالیات آیتم
        item_taxable = item_subtotal - item_discount
        if item_taxable < Decimal('0'):
            item_taxable = Decimal('0')
        item_tax_amount = (item_taxable * transaction.tax / Decimal('100')).quantize(Decimal('0.01'))
        tax_amount += item_tax_amount
    
    # محاسبات نهایی
    net_amount = subtotal - discount_total
    if net_amount < Decimal('0'):
        net_amount = Decimal('0')
    
    # استفاده از مقادیر ذخیره شده در تراکنش یا محاسبه مجدد
    total_amount = transaction.total_amount or (net_amount + tax_amount)
    advance = transaction.advance or Decimal('0')
    balance = transaction.balance or (total_amount - advance)
    
    # وضعیت پرداخت
    if advance >= total_amount and total_amount > Decimal('0'):
        payment_status = 'paid'
    elif advance > Decimal('0'):
        payment_status = 'partial'
    else:
        payment_status = 'unpaid'
    
    # روزهای گذشته
    today = timezone.now().date()
    if transaction.date:
        days_passed = (today - transaction.date).days
    else:
        days_passed = 0
    
    # محاسبه درصد پرداخت شده
    paid_percentage = Decimal('0')
    if total_amount > Decimal('0'):
        paid_percentage = (advance / total_amount) * Decimal('100')
    
    context = {
        'transaction': transaction,
        'items': items,
        'subtotal': subtotal,
        'discount_total': discount_total,
        'tax_amount': tax_amount,
        'total_amount': total_amount,
        'advance': advance,
        'balance': balance,
        'payment_status': payment_status,
        'today': today,
        'days_passed': days_passed,
        'created_by': transaction.created_by,
        'paid_percentage': paid_percentage,
    }
    
    return render(request, 'daily_sale/invoice.html', context)
@login_required
def download_invoice_pdf(request, pk):
    transaction = get_object_or_404(
        DailySaleTransaction.objects.select_related('company', 'customer', 'created_by'),
        pk=pk
    )
    items = transaction.items.all().select_related('item', 'container')
    
    paid_percentage = Decimal('0')
    if transaction.total_amount > Decimal('0'):
        paid_percentage = (transaction.advance / transaction.total_amount) * Decimal('100')
    
    try:
        qr_data = f"""
        Invoice: {transaction.invoice_number}
        Amount: {transaction.total_amount} AED
        Date: {transaction.date}
        """
        qr = qrcode.make(qr_data)
        buffered = BytesIO()
        qr.save(buffered, format="PNG")
        qr_code_base64 = base64.b64encode(buffered.getvalue()).decode()
    except:
        qr_code_base64 = None
    
    context = {
        'transaction': transaction,
        'items': items,
        'paid_percentage': round(paid_percentage, 2),
        'qr_code': qr_code_base64,
        'today': timezone.now().date(),
        'days_passed': (timezone.now().date() - transaction.date).days if transaction.date else 0,
        'created_by': transaction.created_by,
        'is_pdf': True,
        'subtotal': transaction.subtotal or Decimal('0'),
        'tax_amount': transaction.tax_amount or Decimal('0'),
        'total_amount': transaction.total_amount or Decimal('0'),
        'advance': transaction.advance or Decimal('0'),
        'balance': transaction.balance or Decimal('0'),
        'tax_rate': transaction.tax or Decimal('5'),
    }
    
    html_string = render_to_string('daily_sale/invoice.html', context)
    result = BytesIO()
    pdf = pisa.pisaDocument(
        BytesIO(html_string.encode("UTF-8")), 
        result,
        encoding='UTF-8'
    )
    
    if not pdf.err:
        response = HttpResponse(
            result.getvalue(), 
            content_type='application/pdf'
        )
        filename = f"Invoice_{transaction.invoice_number or transaction.id}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    return HttpResponse('Error generating PDF', status=500)


@login_required
def detail_view(request, pk):
    transaction = get_object_or_404(
        DailySaleTransaction.objects.select_related(
            'company', 
            'customer', 
            'created_by',
            'container'
        ),
        pk=pk
    )

    items = transaction.items.all().select_related(
        'item',
        'container'
    ).order_by('id')
    
    # محاسبات واقعی از دیتابیس
    subtotal = Decimal('0')
    discount_total = Decimal('0')
    tax_amount = Decimal('0')
    
    for item in items:
        # محاسبه سابتوتال از دیتابیس
        item_subtotal = item.quantity * item.unit_price
        subtotal += item_subtotal
        
        # تخفیف
        item_discount = item.discount or Decimal('0')
        discount_total += item_discount
        
        # مالیات آیتم
        item_taxable = item_subtotal - item_discount
        if item_taxable < Decimal('0'):
            item_taxable = Decimal('0')
        item_tax_amount = (item_taxable * transaction.tax / Decimal('100')).quantize(Decimal('0.01'))
        tax_amount += item_tax_amount
    
    # محاسبات نهایی
    net_amount = subtotal - discount_total
    if net_amount < Decimal('0'):
        net_amount = Decimal('0')
    
    # استفاده از مقادیر ذخیره شده در تراکنش یا محاسبه مجدد
    total_amount = transaction.total_amount or (net_amount + tax_amount)
    advance = transaction.advance or Decimal('0')
    balance = transaction.balance or (total_amount - advance)
    
    # وضعیت پرداخت
    if advance >= total_amount and total_amount > Decimal('0'):
        payment_status = 'paid'
    elif advance > Decimal('0'):
        payment_status = 'partial'
    else:
        payment_status = 'unpaid'
    
    # روزهای گذشته
    today = timezone.now().date()
    if transaction.date:
        days_passed = (today - transaction.date).days
    else:
        days_passed = 0
    
    # محاسبه درصد پرداخت شده
    paid_percentage = Decimal('0')
    if total_amount > Decimal('0'):
        paid_percentage = (advance / total_amount) * Decimal('100')
    
    context = {
        'transaction': transaction,
        'items': items,
        'subtotal': subtotal,
        'discount_total': discount_total,
        'tax_amount': tax_amount,
        'total_amount': total_amount,
        'advance': advance,
        'balance': balance,
        'payment_status': payment_status,
        'today': today,
        'days_passed': days_passed,
        'created_by': transaction.created_by,
        'paid_percentage': paid_percentage,
    }
    
    return render(request, 'daily_sale/detail.html', context)