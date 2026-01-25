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
import base64
from containers .models import Container
from django.http import JsonResponse, HttpResponse
from django.core.paginator import Paginator
from django.utils import timezone
from decimal import Decimal,ROUND_HALF_UP
from django.db.models import Sum, Q, F, Count, Avg
from django.db import connection
import json
from datetime import datetime, timedelta
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
    if request.method == "POST":
        print("=" * 50)
        print("DEBUG: Transaction Create POST Request")
        print(f"Form data keys: {list(request.POST.keys())}")
        items_data_raw = request.POST.get("items_data", "[]")
        print(f"DEBUG: items_data raw: {items_data_raw}")
        
        try:
            items_list = json.loads(items_data_raw)
            print(f"DEBUG: Parsed items_list: {items_list}")
            print(f"DEBUG: Number of items: {len(items_list)}")
            
            for i, item in enumerate(items_list):
                print(f"DEBUG: Item {i}: {item}")
                print(f"DEBUG:   item_id: {item.get('item_id')}, type: {type(item.get('item_id'))}")
                
        except Exception as e:
            print(f"DEBUG: JSON parse error: {e}")
        
        print("=" * 50)
        
        form = DailySaleTransactionForm(request.POST)

        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.created_by = request.user
            transaction.subtotal = Decimal(request.POST.get("subtotal", "0"))
            transaction.tax_amount = Decimal(request.POST.get("tax_amount", "0"))
            transaction.total_amount = Decimal(request.POST.get("total_amount", "0"))
            transaction.balance = Decimal(request.POST.get("balance", "0"))
            transaction.advance = Decimal(request.POST.get("advance", "0") or "0")

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
            if transaction.advance > Decimal("0"):
                Payment.objects.create(
                    transaction=transaction,
                    amount=transaction.advance,
                    method=request.POST.get("payment_method", "cash"),
                    date=transaction.date,
                    created_by=request.user,
                    note=f"Initial payment for invoice {transaction.invoice_number or 'N/A'}"
                )
            items_json = request.POST.get("items_data", "[]")
            items_created = 0

            try:
                items_list = json.loads(items_json)
                print(f"✅ Parsed items list: {items_list}")
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error: {e}")
                messages.error(request, "Invalid items data format.")
                transaction.delete()
                return render(request, "daily_sale/transaction_create.html", {"form": form})
            for item_data in items_list:
                print(f"🔍 Processing item data: {item_data}")
                raw_item_id = item_data.get("item_id")
                if not raw_item_id:
                    print("⚠️ No item_id found")
                    continue
                item_id = raw_item_id 
                print(f"  Looking for inventory with UUID: {item_id}")
                
                try:
                    inventory = Inventory_List.objects.get(pk=item_id)
                    print(f"  ✅ Inventory found: {inventory.product_name} (UUID: {inventory.id})")
                except Inventory_List.DoesNotExist:
                    print(f"  ❌ Inventory not found for UUID: {item_id}")
                    try:
                        available_items = Inventory_List.objects.all()[:3]
                        print(f"  Available items (first 3):")
                        for avail in available_items:
                            print(f"    - {avail.id}: {avail.product_name}")
                    except:
                        print("  Could not list available items")
                    
                    continue
                except ValueError as e:
                    print(f"  ❌ Invalid UUID format: {item_id} - Error: {e}")
                    continue
                quantity = Decimal(str(item_data.get("quantity", 1)))
                unit_price = Decimal(str(item_data.get("unit_price", 0)))
                discount = Decimal(str(item_data.get("discount", 0)))
                subtotal = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                taxable = (subtotal - discount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if taxable < Decimal("0"):
                    taxable = Decimal("0")

                tax_amount = (taxable * transaction.tax / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                total = (taxable + tax_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                container_obj = inventory.container if inventory.container else None
                try:
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
                    print(f"  ✅ Item created successfully")
                except Exception as e:
                    print(f"  ❌ Error saving item: {str(e)}")
                    continue
            if items_created == 0:
                print(f"❌ No items created, rolling back transaction")
                messages.error(request, "No valid item found. Please check the items you selected.")
                transaction.delete()
                return render(request, "daily_sale/transaction_create.html", {"form": form})
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
            messages.success(
                request,
                f"✅ Transaction #{transaction.invoice_number} created successfully with {items_created} item(s)."
            )

            try:
                recompute_daily_summary_for_date(transaction.date)
                if transaction.customer:
                    recompute_outstanding_for_customer(transaction.customer.id)
            except Exception as e:
                print(f"⚠️ Error in summary recompute: {e}")

            logger.info(
                f"Transaction #{transaction.invoice_number} created. Advance: {transaction.advance}, Total: {transaction.total_amount}, Balance: {transaction.balance}"
            )

            return redirect("daily_sale:transaction_detail", pk=transaction.pk)

        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    form = DailySaleTransactionForm(initial={
        "date": timezone.now().date(),
        "tax": Decimal("5.00"),
        "due_date": timezone.now().date() + timezone.timedelta(days=30),
    })

    return render(request, "daily_sale/transaction_create.html", {"form": form})

@login_required
def invoice_pdf(request, pk):
    tx = get_object_or_404(DailySaleTransaction, pk=pk)

    template = get_template("daily_sale/invoice_pdf.html")
    html = template.render({"tx": tx})

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'filename="invoice_{tx.invoice_number}.pdf"'
    return response

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


def recompute_daily_summary_for_date(target_date):
    if not target_date:
        logger.warning("recompute_daily_summary_for_date called with no date")
        return None

    try:
        qs = DailySaleTransaction.objects.filter(date=target_date)
        if not qs.exists():
            DailySummary.objects.filter(date=target_date).delete()
            logger.info(f"No transactions found for {target_date}, summary deleted.")
            return None
        agg = qs.aggregate(
            total_sales=Sum("total_amount", filter=Q(transaction_type="sale")),
            total_purchases=Sum("total_amount", filter=Q(transaction_type="purchase")),
            items_sold=Sum("quantity", filter=Q(transaction_type="sale")),
            transactions_count=Count("id"),
        )
        total_sales = agg.get("total_sales") or Decimal("0")
        total_purchases = agg.get("total_purchases") or Decimal("0")
        items_sold = agg.get("items_sold") or 0
        transactions_count = agg.get("transactions_count") or 0
        total_profit = total_sales - total_purchases
        payments = Payment.objects.filter(transaction__date=target_date)
        total_paid = payments.aggregate(sum=Sum("amount"))["sum"] or Decimal("0")
        net_balance = total_sales - total_paid
        customers_count = qs.filter(customer__isnull=False).values("customer").distinct().count()
        summary, created = DailySummary.objects.update_or_create(
            date=target_date,
            defaults={
                "total_sales": total_sales,
                "total_purchases": total_purchases,
                "total_profit": total_profit,
                "net_balance": net_balance,
                "transactions_count": transactions_count,
                "items_sold": items_sold,
                "customers_count": customers_count,
                "updated_at": timezone.now(),
            },
        )

        if created:
            logger.info(f"Created daily summary for {target_date}")
        else:
            logger.info(f"Updated daily summary for {target_date}")

        return summary
    except Exception as e:
        logger.error(f"Error recomputing daily summary for {target_date}: {e}", exc_info=True)
        return None

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
    try:
        filter_type = request.GET.get('filter', '')
        search_query = request.GET.get('search', '')
        sort_by = request.GET.get('sort', 'debt_desc')
        customer_profiles = UserProfile.objects.filter(
            role=UserProfile.ROLE_CUSTOMER
        ).select_related('user')
        outstanding_customers = []
        total_amount = Decimal('0')
        total_paid = Decimal('0')
        total_discount = Decimal('0')
        total_remaining = Decimal('0')

        for customer in customer_profiles:
            customer_transactions = DailySaleTransaction.objects.filter(
                customer=customer
            ).select_related('item', 'container').order_by('-date')            
            customer_total = Decimal('0')
            customer_paid = Decimal('0')
            customer_discount = Decimal('0')
            for tx in customer_transactions:
                paid_amount = Payment.objects.filter(transaction=tx).aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0')
                remaining = (tx.total_amount or Decimal('0')) - paid_amount - (tx.discount or Decimal('0'))
                if remaining > Decimal('0'):
                    customer_total += tx.total_amount or Decimal('0')
                    customer_paid += paid_amount
                    customer_discount += tx.discount or Decimal('0')
            remaining_amount = customer_total - customer_paid - customer_discount
            if remaining_amount > Decimal('0'):
                customer_data = {
                    'customer_id': customer.id,
                    'customer_name': customer.user.get_full_name() if customer.user else customer.display_name,
                    'remaining_amount': float(remaining_amount),  # تبدیل به float برای JSON
                    'total_amount': float(customer_total),
                    'paid_amount': float(customer_paid),
                    'discount_amount': float(customer_discount),
                    'payment_status': 'partial',
                }
                outstanding_customers.append(customer_data)
            total_amount += customer_total
            total_paid += customer_paid
            total_discount += customer_discount
            total_remaining += remaining_amount
        if filter_type:
            if filter_type == 'paid':
                outstanding_customers = [c for c in outstanding_customers if c['payment_status'] == 'paid']
            elif filter_type == 'partial':
                outstanding_customers = [c for c in outstanding_customers if c['payment_status'] == 'partial']
        if search_query:
            outstanding_customers = [
                c for c in outstanding_customers
                if search_query.lower() in c['customer_name'].lower()
            ]
        if sort_by == 'debt_desc':
            outstanding_customers.sort(key=lambda x: x['remaining_amount'], reverse=True)
        elif sort_by == 'debt_asc':
            outstanding_customers.sort(key=lambda x: x['remaining_amount'])
        total_outstanding = total_remaining
        customers_count = len(outstanding_customers)
        avg_debt = total_remaining / customers_count if customers_count > 0 else Decimal('0')
        customers_json = json.dumps(outstanding_customers, ensure_ascii=False)
        context = {
            'outstanding_customers': outstanding_customers,
            'total_outstanding': total_outstanding,
            'avg_debt': avg_debt,
            'total_amount': total_amount,
            'total_paid': total_paid,
            'total_discount': total_discount,
            'total_remaining': total_remaining,
            'customers_count': customers_count,
            'filter_type': filter_type,
            'search_query': search_query,
            'sort_by': sort_by,
            'customers_json': customers_json,
        }
        return render(request, "daily_sale/outstanding_customers.html", context)
    
    except Exception as e:
        logger.error(f"Error in outstanding_view: {str(e)}", exc_info=True)
        context = {
            'outstanding_customers': [],
            'total_outstanding': Decimal('0'),
            'avg_debt': Decimal('0'),
            'total_amount': Decimal('0'),
            'total_paid': Decimal('0'),
            'total_discount': Decimal('0'),
            'total_remaining': Decimal('0'),
            'customers_count': 0,
            'customers_json': '[]',
            'error': True,
            'error_message': f'Erro In Loading Date!: {str(e)}',
        }
        return render(request, "daily_sale/old_transactions.html", context)

def calculate_date_range(period, today):
    if period == 'today':
        start_date = today
        end_date = today
    elif period == 'yesterday':
        start_date = today - timedelta(days=1)
        end_date = start_date
    elif period == 'week':
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=6)
    elif period == 'last_week':
        start_date = today - timedelta(days=today.weekday() + 7)
        end_date = start_date + timedelta(days=6)
    elif period == 'month':
        start_date = today.replace(day=1)
        end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    elif period == 'last_month':
        first_day_current_month = today.replace(day=1)
        end_date = first_day_current_month - timedelta(days=1)
        start_date = end_date.replace(day=1)
    elif period == 'quarter':
        current_quarter = (today.month - 1) // 3 + 1
        start_date = today.replace(month=((current_quarter - 1) * 3 + 1), day=1)
        end_date = (start_date + timedelta(days=92)).replace(day=1) - timedelta(days=1)
    elif period == 'year':
        start_date = today.replace(month=1, day=1)
        end_date = today.replace(month=12, day=31)
    elif period == 'last_year':
        start_date = today.replace(year=today.year-1, month=1, day=1)
        end_date = today.replace(year=today.year-1, month=12, day=31)
    else:  # 'all'
        start_date = today - timedelta(days=365*5)  # 5 years
        end_date = today
    
    return start_date, end_date


def get_customer_name(customer):
    if not customer:
        return 'Unknown'
    if customer.user:
        full_name = customer.user.get_full_name()
        if full_name:
            return full_name
    return customer.display_name if customer.display_name else f'Customer #{customer.id}'

def calculate_transaction_statistics(transactions):
    if not transactions:
        return {
            'total_amount': Decimal('0'),
            'avg_amount': Decimal('0'),
            'total_transactions': 0,
            'full_payments': 0,
            'partial_payments': 0,
            'avg_days_to_settle': 0,
            'fastest_settlement': 0,
            'slowest_settlement': 0,
            'total_customers': 0,
            'avg_payments_per_transaction': 0,
            'total_discount': Decimal('0'),
            'collection_efficiency': 0,
            'top_customers': [],
            'daily_average': Decimal('0'),
            'weekly_average': Decimal('0'),
            'monthly_average': Decimal('0'),
        }
    
    total_amount = sum(t['total_amount'] for t in transactions)
    full_payments = sum(1 for t in transactions if t['settlement_type'] == 'full')
    partial_payments = sum(1 for t in transactions if t['settlement_type'] == 'partial')
    days_to_settle = [t['days_to_settle'] for t in transactions if t['days_to_settle'] > 0]
    avg_days_to_settle = sum(days_to_settle) / len(days_to_settle) if days_to_settle else 0
    fastest_settlement = min(days_to_settle) if days_to_settle else 0
    slowest_settlement = max(days_to_settle) if days_to_settle else 0
    customer_names = [t['customer_name'] for t in transactions]
    unique_customers = len(set(customer_names))
    total_payment_count = sum(t['payment_count'] for t in transactions)
    avg_payments_per_transaction = total_payment_count / len(transactions) if transactions else 0
    total_discount = sum(t.get('discount_amount', Decimal('0')) for t in transactions)
    if total_amount > 0:
        collection_efficiency = ((total_amount - total_discount) / total_amount * 100)
    else:
        collection_efficiency = 0
    customer_totals = {}
    for t in transactions:
        customer_name = t['customer_name']
        if customer_name not in customer_totals:
            customer_totals[customer_name] = Decimal('0')
        customer_totals[customer_name] += t['total_amount']
    
    top_customers = sorted(
        [{'name': name, 'total': float(total)} for name, total in customer_totals.items()],
        key=lambda x: x['total'],
        reverse=True
    )[:5]
    if transactions:
        dates = [t['date'] for t in transactions if t['date']]
        if dates:
            min_date = min(dates)
            max_date = max(dates)
            days_diff = (max_date - min_date).days + 1
            
            if days_diff > 0:
                daily_average = total_amount / days_diff
                weekly_average = total_amount / (days_diff / 7)
                monthly_average = total_amount / (days_diff / 30)
            else:
                daily_average = weekly_average = monthly_average = Decimal('0')
        else:
            daily_average = weekly_average = monthly_average = Decimal('0')
    else:
        daily_average = weekly_average = monthly_average = Decimal('0')
    
    return {
        'total_amount': total_amount,
        'avg_amount': total_amount / len(transactions) if transactions else Decimal('0'),
        'total_transactions': len(transactions),
        'full_payments': full_payments,
        'partial_payments': partial_payments,
        'full_payment_percentage': (full_payments / len(transactions) * 100) if transactions else 0,
        'partial_payment_percentage': (partial_payments / len(transactions) * 100) if transactions else 0,
        'avg_days_to_settle': avg_days_to_settle,
        'fastest_settlement': fastest_settlement,
        'slowest_settlement': slowest_settlement,
        'total_customers': unique_customers,
        'avg_payments_per_transaction': avg_payments_per_transaction,
        'total_discount': total_discount,
        'collection_efficiency': collection_efficiency,
        'top_customers': top_customers,
        'daily_average': daily_average,
        'weekly_average': weekly_average,
        'monthly_average': monthly_average,
    }


def get_transaction_type_stats(transactions):
    stats = {
        'by_month': {},
        'by_customer': {},
        'by_settlement_type': {
            'full': 0,
            'partial': 0
        },
        'by_payment_count': {},
    }
    
    for tx in transactions:
        month_key = tx['date'].strftime('%Y-%m') if tx['date'] else 'Unknown'
        if month_key not in stats['by_month']:
            stats['by_month'][month_key] = Decimal('0')
        stats['by_month'][month_key] += tx['total_amount']
        customer_name = tx['customer_name']
        if customer_name not in stats['by_customer']:
            stats['by_customer'][customer_name] = {
                'total_amount': Decimal('0'),
                'count': 0,
                'avg_days_to_settle': 0
            }
        stats['by_customer'][customer_name]['total_amount'] += tx['total_amount']
        stats['by_customer'][customer_name]['count'] += 1
        stats['by_settlement_type'][tx['settlement_type']] += 1
        payment_count = tx['payment_count']
        if payment_count not in stats['by_payment_count']:
            stats['by_payment_count'][payment_count] = 0
        stats['by_payment_count'][payment_count] += 1
    
    return stats

def paginate_transactions(request, transactions, per_page=20):
    paginator = Paginator(transactions, per_page)
    page = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    
    return page_obj


def get_performance_rating(days_to_settle):
    if days_to_settle <= 7:
        return {'rating': 'Excellent', 'color': 'success', 'score': 5}
    elif days_to_settle <= 14:
        return {'rating': 'Good', 'color': 'info', 'score': 4}
    elif days_to_settle <= 30:
        return {'rating': 'Average', 'color': 'warning', 'score': 3}
    elif days_to_settle <= 60:
        return {'rating': 'Poor', 'color': 'danger', 'score': 2}
    else:
        return {'rating': 'Very Poor', 'color': 'dark', 'score': 1}

def get_customer_list():
    customers = UserProfile.objects.filter(
        role=UserProfile.ROLE_CUSTOMER
    ).select_related('user').order_by('user__first_name')
    
    customer_list = []
    for customer in customers:
        customer_list.append({
            'id': customer.id,
            'name': get_customer_name(customer),
            'email': customer.user.email if customer.user else '',
            'phone': customer.phone if hasattr(customer, 'phone') else ''
        })
    
    return customer_list

@login_required
def cleared_transactions(request):
    try:
        period = request.GET.get('period', 'month')
        customer_id = request.GET.get('customer')
        settlement_type = request.GET.get('type', '')
        sort_by = request.GET.get('sort', 'date_desc')
        search_query = request.GET.get('search', '')
        export_format = request.GET.get('export')
        show_details = request.GET.get('details', 'false') == 'true'
        today = timezone.now().date()
        start_date, end_date = calculate_date_range(period, today)
        transactions_qs = DailySaleTransaction.objects.filter(
            date__range=[start_date, end_date],
            total_amount__gt=0 
        ).select_related(
            'customer__user', 
            'item', 
            'company', 
            'container'
        ).prefetch_related(
            'payments'
        ).order_by('-date')
        if search_query:
            transactions_qs = transactions_qs.filter(
                Q(invoice_number__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(customer__user__first_name__icontains=search_query) |
                Q(customer__user__last_name__icontains=search_query) |
                Q(customer__display_name__icontains=search_query)
            )
        if customer_id and customer_id.isdigit():
            transactions_qs = transactions_qs.filter(customer_id=int(customer_id))
        cleared_transactions_list = []
        transaction_details = {}
        
        for tx in transactions_qs:
            paid_amount = Payment.objects.filter(transaction=tx).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')
            discount_amount = tx.discount or Decimal('0')
            remaining = (tx.total_amount or Decimal('0')) - paid_amount - discount_amount
            if remaining <= Decimal('0') and tx.total_amount > Decimal('0'):
                last_payment = Payment.objects.filter(transaction=tx).order_by('-date').first()
                days_to_settle = 0
                settlement_date = None
                
                if last_payment:
                    settlement_date = last_payment.date
                    days_to_settle = (settlement_date.date() - tx.date).days
                payment_count = Payment.objects.filter(transaction=tx).count()
                settlement_type_display = 'full' if payment_count == 1 else 'partial'
                customer_name = get_customer_name(tx.customer)
                performance = get_performance_rating(days_to_settle)
                transaction_data = {
                    'id': tx.id,
                    'invoice_number': tx.invoice_number or f'INV-{tx.id:06d}',
                    'date': tx.date,
                    'due_date': tx.due_date,
                    'total_amount': tx.total_amount or Decimal('0'),
                    'customer_name': customer_name,
                    'customer_id': tx.customer.id if tx.customer else None,
                    'paid_amount': paid_amount,
                    'discount_amount': discount_amount,
                    'payment_count': payment_count,
                    'settlement_date': settlement_date,
                    'days_to_settle': days_to_settle,
                    'settlement_type': settlement_type_display,
                    'performance_rating': performance['rating'],
                    'performance_color': performance['color'],
                    'performance_score': performance['score'],
                    'description': tx.description or '',
                    'item_name': tx.item.name if tx.item else 'N/A',
                    'company_name': tx.company.name if tx.company else 'N/A',
                    'container_name': tx.container.name if tx.container else 'N/A',
                }
                
                cleared_transactions_list.append(transaction_data)
                transaction_details[tx.id] = transaction_data
        if settlement_type:
            cleared_transactions_list = [
                t for t in cleared_transactions_list 
                if t['settlement_type'] == settlement_type
            ]
        if sort_by == 'date_desc':
            cleared_transactions_list.sort(key=lambda x: x['date'], reverse=True)
        elif sort_by == 'date_asc':
            cleared_transactions_list.sort(key=lambda x: x['date'])
        elif sort_by == 'amount_desc':
            cleared_transactions_list.sort(key=lambda x: x['total_amount'], reverse=True)
        elif sort_by == 'amount_asc':
            cleared_transactions_list.sort(key=lambda x: x['total_amount'])
        elif sort_by == 'days_desc':
            cleared_transactions_list.sort(key=lambda x: x['days_to_settle'], reverse=True)
        elif sort_by == 'days_asc':
            cleared_transactions_list.sort(key=lambda x: x['days_to_settle'])
        elif sort_by == 'customer':
            cleared_transactions_list.sort(key=lambda x: x['customer_name'])
        elif sort_by == 'performance':
            cleared_transactions_list.sort(key=lambda x: x['performance_score'], reverse=True)
        cleared_stats = calculate_transaction_statistics(cleared_transactions_list)
        type_stats = get_transaction_type_stats(cleared_transactions_list)
        page_obj = paginate_transactions(request, cleared_transactions_list, 20)
        customer_list = get_customer_list()
        transactions_json = json.dumps([
            {
                'id': tx['id'],
                'invoice_number': tx['invoice_number'],
                'date': tx['date'].strftime('%Y-%m-%d') if tx['date'] else '',
                'total_amount': float(tx['total_amount']),
                'customer_name': tx['customer_name'],
                'settlement_type': tx['settlement_type'],
                'days_to_settle': tx['days_to_settle'],
                'payment_count': tx['payment_count'],
                'settlement_date': tx['settlement_date'].strftime('%Y-%m-%d') if tx['settlement_date'] else '',
                'performance_rating': tx['performance_rating'],
                'performance_color': tx['performance_color'],
            }
            for tx in cleared_transactions_list[:100]
        ], ensure_ascii=False)
        monthly_stats_json = json.dumps([
            {'month': month, 'amount': float(amount)}
            for month, amount in sorted(type_stats['by_month'].items())
        ], ensure_ascii=False)
        
        context = {
            'page_obj': page_obj,
            'cleared_transactions': page_obj.object_list,
            'cleared_stats': cleared_stats,
            'type_stats': type_stats,
            'search_query': search_query,
            'period': period,
            'customer_id': customer_id,
            'settlement_type': settlement_type,
            'sort_by': sort_by,
            'start_date': start_date,
            'end_date': end_date,
            'customer_list': customer_list,
            'transactions_json': transactions_json,
            'monthly_stats_json': monthly_stats_json,
            'today': today,
            'show_details': show_details,
        }
        
        return render(request, "daily_sale/cleared_transactions.html", context)
    
    except Exception as e:
        logger.error(f"Error in cleared_transactions: {str(e)}", exc_info=True)
        context = {
            'page_obj': None,
            'cleared_transactions': [],
            'cleared_stats': {
                'total_amount': Decimal('0'),
                'total_transactions': 0,
                'total_customers': 0,
                'avg_days_to_settle': 0,
                'collection_efficiency': 0,
            },
            'error': True,
            'error_message': f'Error In Loadong Date: {str(e)}',
            'today': timezone.now().date(),
        }
        return render(request, "daily_sale/cleared_transactions.html", context)


@login_required
def get_transaction_details(request, transaction_id):
    try:
        transaction = DailySaleTransaction.objects.get(id=transaction_id)
        payments = Payment.objects.filter(transaction=transaction).order_by('date')
        total_paid = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0')
        remaining = (transaction.total_amount or Decimal('0')) - total_paid - (transaction.discount or Decimal('0'))
        payment_details = []
        for payment in payments:
            payment_details.append({
                'date': payment.date.strftime('%Y-%m-%d'),
                'amount': float(payment.amount),
                'method': payment.get_payment_method_display() if hasattr(payment, 'get_payment_method_display') else 'N/A',
                'reference': payment.reference or '',
                'notes': payment.notes or '',
            })
        transaction_data = {
            'id': transaction.id,
            'invoice_number': transaction.invoice_number or f'INV-{transaction.id:06d}',
            'date': transaction.date.strftime('%Y-%m-%d'),
            'due_date': transaction.due_date.strftime('%Y-%m-%d') if transaction.due_date else '',
            'total_amount': float(transaction.total_amount or Decimal('0')),
            'discount': float(transaction.discount or Decimal('0')),
            'description': transaction.description or '',
            'customer_name': get_customer_name(transaction.customer),
            'customer_phone': transaction.customer.phone if transaction.customer and hasattr(transaction.customer, 'phone') else '',
            'customer_email': transaction.customer.user.email if transaction.customer and transaction.customer.user else '',
            'item_name': transaction.item.name if transaction.item else '',
            'item_quantity': transaction.quantity,
            'item_price': float(transaction.unit_price or Decimal('0')),
            'company_name': transaction.company.name if transaction.company else '',
            'container_name': transaction.container.name if transaction.container else '',
            'total_paid': float(total_paid),
            'remaining': float(remaining),
            'is_cleared': remaining <= Decimal('0'),
            'payment_count': len(payments),
            'payment_details': payment_details,
        }
        
        return JsonResponse({
            'success': True,
            'transaction': transaction_data
        })
        
    except DailySaleTransaction.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Transaction not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error getting transaction details: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def cleared_transactions_export(request):
    try:
        export_format = request.GET.get('format', 'excel')
        period = request.GET.get('period', 'month')
        today = timezone.now().date()
        start_date, end_date = calculate_date_range(period, today)
        transactions = DailySaleTransaction.objects.filter(
            date__range=[start_date, end_date]
        ).select_related('customer__user', 'item', 'company', 'container')
        cleared_data = []
        for tx in transactions:
            paid_amount = Payment.objects.filter(transaction=tx).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')
            
            remaining = (tx.total_amount or Decimal('0')) - paid_amount - (tx.discount or Decimal('0'))
            
            if remaining <= Decimal('0') and tx.total_amount > Decimal('0'):
                cleared_data.append({
                    'Invoice Number': tx.invoice_number or f'INV-{tx.id}',
                    'Date': tx.date.strftime('%Y-%m-%d'),
                    'Customer': get_customer_name(tx.customer),
                    'Total Amount': float(tx.total_amount or Decimal('0')),
                    'Paid Amount': float(paid_amount),
                    'Discount': float(tx.discount or Decimal('0')),
                    'Description': tx.description or '',
                    'Item': tx.item.name if tx.item else '',
                    'Company': tx.company.name if tx.company else '',
                    'Settlement Status': 'Cleared',
                })
        return JsonResponse({
            'success': True,
            'message': f'Exported {len(cleared_data)} transactions',
            'data': cleared_data[:10] 
        })
        
    except Exception as e:
        logger.error(f"Error exporting cleared transactions: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def cleared_transactions_summary(request):
    try:
        period = request.GET.get('period', 'month')
        today = timezone.now().date()
        start_date, end_date = calculate_date_range(period, today)
        transactions = DailySaleTransaction.objects.filter(
            date__range=[start_date, end_date]
        )     
        cleared_count = 0
        total_cleared_amount = Decimal('0')
        for tx in transactions:
            paid_amount = Payment.objects.filter(transaction=tx).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')
            
            remaining = (tx.total_amount or Decimal('0')) - paid_amount - (tx.discount or Decimal('0'))
            
            if remaining <= Decimal('0') and tx.total_amount > Decimal('0'):
                cleared_count += 1
                total_cleared_amount += tx.total_amount or Decimal('0')
        weekly_data = []
        for i in range(4):
            week_start = today - timedelta(days=today.weekday() + (i * 7))
            week_end = week_start + timedelta(days=6)
            
            week_transactions = DailySaleTransaction.objects.filter(
                date__range=[week_start, week_end]
            )
            
            week_cleared_amount = Decimal('0')
            for tx in week_transactions:
                paid_amount = Payment.objects.filter(transaction=tx).aggregate(
                    total=Sum('amount')
                )['total'] or Decimal('0')
                
                remaining = (tx.total_amount or Decimal('0')) - paid_amount - (tx.discount or Decimal('0'))
                if remaining <= Decimal('0') and tx.total_amount > Decimal('0'):
                    week_cleared_amount += tx.total_amount or Decimal('0')
            weekly_data.append({
                'week': f'Week {i+1}',
                'amount': float(week_cleared_amount)
            })
        
        return JsonResponse({
            'success': True,
            'summary': {
                'cleared_count': cleared_count,
                'total_cleared_amount': float(total_cleared_amount),
                'period': period,
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
            },
            'weekly_trend': weekly_data,
            'performance_indicators': {
                'collection_efficiency': 95.5, 
                'avg_settlement_days': 12.3,   
                'customer_satisfaction': 4.5,   
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting cleared transactions summary: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
        
        
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
        DailySaleTransaction.objects.select_related('company', 'customer', 'created_by'),
        pk=pk
    )
    items = transaction.items.all().select_related('item', 'container')
    paid_percentage = Decimal('0')
    if transaction.total_amount > Decimal('0'):
        paid_percentage = (transaction.advance / transaction.total_amount) * Decimal('100')
    
    # QR Code
    try:
        qr_data = f"Invoice: {transaction.invoice_number}\nAmount: {transaction.total_amount} AED\nDate: {transaction.date}"
        qr = qrcode.make(qr_data)
        buffered = BytesIO()
        qr.save(buffered, format="PNG")
        qr_code_base64 = base64.b64encode(buffered.getvalue()).decode()
    except:
        qr_code_base64 = None
    today = timezone.now().date()
    days_passed = (today - transaction.date).days if transaction.date else 0
    
    context = {
        'transaction': transaction,
        'items': items,
        'paid_percentage': round(paid_percentage, 2),
        'qr_code': qr_code_base64,
        'today': today,
        'days_passed': days_passed,
        'created_by': transaction.created_by,
        'subtotal': transaction.subtotal or Decimal('0'),
        'tax_amount': transaction.tax_amount or Decimal('0'),
        'total_amount': transaction.total_amount or Decimal('0'),
        'advance': transaction.advance or Decimal('0'),
        'balance': transaction.balance or Decimal('0'),
        'tax_rate': transaction.tax or Decimal('5'),
    }
    
    return render(request, 'daily_sale/invoice_professional.html', context)


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
        qr_data = f"Invoice: {transaction.invoice_number}\nAmount: {transaction.total_amount} AED\nDate: {transaction.date}"
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
    html_string = render_to_string('daily_sale/invoice_professional.html', context)
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