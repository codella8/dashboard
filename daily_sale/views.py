# daily_sale/views.py
from decimal import Decimal
from datetime import datetime, timedelta
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import (
    Sum, Count, Avg, Q, F, Case, When, Value, DecimalField, Max
)
from django.db.models.functions import Coalesce
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest

from .models import DailySaleTransaction, DailySummary
from .forms import DailySaleTransactionForm

# optional: use report helpers if present
try:
    from .daily_sale_report import (
        compute_and_save_daily_summary,
        compute_daily_aggregates,
        get_sales_summary,
        sales_by_item as report_sales_by_item,
        sales_timeseries as report_sales_timeseries,
        outstanding_customers as report_outstanding_customers,
    )
    REPORTS_AVAILABLE = True
except Exception:
    REPORTS_AVAILABLE = False

DEC_ZERO = Decimal("0.00")
logger = logging.getLogger(__name__)


# ----------------------
# helpers
# ----------------------
def _parse_date_param(val, default):
    """
    Accepts: None, date object, 'YYYY-MM-DD' string.
    Returns a date object or default on failure.
    """
    if not val:
        return default
    if hasattr(val, 'year'):
        return val
    try:
        return datetime.fromisoformat(val).date()
    except Exception:
        try:
            # fallback: parse common formats
            return datetime.strptime(val, "%Y-%m-%d").date()
        except Exception:
            return default


def _decimal_or_zero(v):
    try:
        if v is None:
            return DEC_ZERO
        if isinstance(v, Decimal):
            return v
        return Decimal(v)
    except Exception:
        return DEC_ZERO


def is_admin_user(user):
    return user.is_active and (user.is_staff or user.is_superuser)


# ----------------------
# CRUD: Transactions
# ----------------------
@login_required
def transaction_list_view(request):
    """
    List transactions with optional filters and pagination.
    Filters: date, start_date/end_date, transaction_type, customer_id, invoice (search).
    """
    qs = DailySaleTransaction.objects.all().select_related(
        'item', 'customer__user', 'container', 'company', 'saraf'
    ).order_by('-date', '-created_at')

    # filters
    invoice_q = request.GET.get('q') or request.GET.get('invoice')
    if invoice_q:
        qs = qs.filter(invoice_number__icontains=invoice_q)

    tx_type = request.GET.get('type')
    if tx_type in ['sale', 'purchase', 'return']:
        qs = qs.filter(transaction_type=tx_type)

    customer_id = request.GET.get('customer_id')
    if customer_id:
        qs = qs.filter(customer_id=customer_id)

    # date filters
    start = request.GET.get('start_date')
    end = request.GET.get('end_date')
    if start or end:
        start_date = _parse_date_param(start, None)
        end_date = _parse_date_param(end, None)
        if start_date and end_date:
            qs = qs.filter(date__range=[start_date, end_date])
        elif start_date:
            qs = qs.filter(date__gte=start_date)
        elif end_date:
            qs = qs.filter(date__lte=end_date)

    # pagination
    page = request.GET.get('page', 1)
    per_page = int(request.GET.get('per_page', 25))
    paginator = Paginator(qs, per_page)
    try:
        transactions = paginator.page(page)
    except PageNotAnInteger:
        transactions = paginator.page(1)
    except EmptyPage:
        transactions = paginator.page(paginator.num_pages)

    context = {
        'transactions': transactions,
        'paginator': paginator,
        'filters': {
            'q': invoice_q,
            'type': tx_type,
            'customer_id': customer_id,
            'start_date': start,
            'end_date': end,
        }
    }
    return render(request, "daily_sale/transaction_list.html", context)


@login_required
def transaction_create_view(request):
    """
    Create transaction. Auto-calc total_amount and balance if not provided.
    Sets created_by to request.user if not provided.
    After save, attempts to recompute DailySummary for the date (if helper present).
    """
    if request.method == 'POST':
        form = DailySaleTransactionForm(request.POST)
        if form.is_valid():
            instance = form.save(commit=False)
            # compute totals if not provided or zero
            try:
                qty = Decimal(instance.quantity or 0)
                unit = _decimal_or_zero(instance.unit_price)
                discount = _decimal_or_zero(instance.discount)
                tax = _decimal_or_zero(instance.tax)
                advance = _decimal_or_zero(instance.advance)
                paid = _decimal_or_zero(instance.paid)

                subtotal = (qty * unit).quantize(DEC_ZERO)
                after_discount = subtotal - discount
                if after_discount < DEC_ZERO:
                    after_discount = DEC_ZERO
                computed_total = (after_discount + tax).quantize(DEC_ZERO)
                computed_balance = (computed_total - (advance + paid)).quantize(DEC_ZERO)

                if (not instance.total_amount) or instance.total_amount == DEC_ZERO:
                    instance.total_amount = computed_total
                if (not instance.balance) or instance.balance == DEC_ZERO:
                    instance.balance = computed_balance
            except Exception as e:
                logger.exception("Auto-calculation failed on create: %s", e)
                instance.total_amount = instance.total_amount or DEC_ZERO
                instance.balance = instance.balance or DEC_ZERO

            if not instance.created_by and request.user.is_authenticated:
                instance.created_by = request.user

            with transaction.atomic():
                instance.save()
                # try to recompute daily summary
                try:
                    if REPORTS_AVAILABLE:
                        compute_and_save_daily_summary(instance.date)
                except Exception:
                    logger.exception("Failed to update DailySummary after create.")
            return redirect('daily_sale:transaction_list')
    else:
        form = DailySaleTransactionForm(initial={'date': timezone.now().date()})
    return render(request, "daily_sale/transaction_form.html", {'form': form})


@login_required
def transaction_edit_view(request, pk):
    transaction = get_object_or_404(DailySaleTransaction, pk=pk)
    if request.method == 'POST':
        form = DailySaleTransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            instance = form.save(commit=False)
            # recalc if needed
            try:
                qty = Decimal(instance.quantity or 0)
                unit = _decimal_or_zero(instance.unit_price)
                discount = _decimal_or_zero(instance.discount)
                tax = _decimal_or_zero(instance.tax)
                advance = _decimal_or_zero(instance.advance)
                paid = _decimal_or_zero(instance.paid)

                subtotal = (qty * unit).quantize(DEC_ZERO)
                after_discount = subtotal - discount
                if after_discount < DEC_ZERO:
                    after_discount = DEC_ZERO
                computed_total = (after_discount + tax).quantize(DEC_ZERO)
                computed_balance = (computed_total - (advance + paid)).quantize(DEC_ZERO)

                if (not instance.total_amount) or instance.total_amount == DEC_ZERO:
                    instance.total_amount = computed_total
                if (not instance.balance) or instance.balance == DEC_ZERO:
                    instance.balance = computed_balance
            except Exception:
                logger.exception("Auto-calc edit failed.")
                instance.total_amount = instance.total_amount or DEC_ZERO
                instance.balance = instance.balance or DEC_ZERO

            with transaction.atomic():
                instance.save()
                try:
                    if REPORTS_AVAILABLE:
                        compute_and_save_daily_summary(instance.date)
                except Exception:
                    logger.exception("Failed to update DailySummary after edit.")
            return redirect('daily_sale:transaction_list')
    else:
        form = DailySaleTransactionForm(instance=transaction)
    return render(request, "daily_sale/transaction_form.html", {'form': form, 'transaction': transaction})


@login_required
def transaction_delete_view(request, pk):
    transaction = get_object_or_404(DailySaleTransaction, pk=pk)
    if request.method == 'POST':
        tx_date = transaction.date
        with transaction.atomic():
            transaction.delete()
            try:
                if REPORTS_AVAILABLE:
                    compute_and_save_daily_summary(tx_date)
            except Exception:
                logger.exception("Failed to update DailySummary after delete.")
        return redirect('daily_sale:transaction_list')
    return render(request, "daily_sale/transaction_confirm_delete.html", {'transaction': transaction})


# ----------------------
# Dashboards & Reports
# ----------------------
@login_required
@user_passes_test(is_admin_user)
def admin_dashboard(request):
    """
    Admin-only dashboard (company management).
    KPIs, top items, trends, recent transactions.
    """
    today = timezone.now().date()
    date = _parse_date_param(request.GET.get('date'), today)

    # default date range for trend
    days = int(request.GET.get('days', 30))
    start_for_trend = date - timedelta(days=days - 1)

    try:
        # aggregates (ensure DecimalField for decimals)
        if REPORTS_AVAILABLE:
            daily_stats = compute_daily_aggregates(date)
        else:
            qs = DailySaleTransaction.objects.filter(date=date)
            daily_stats = qs.aggregate(
                total_sales=Coalesce(Sum('total_amount', filter=Q(transaction_type='sale')), Value(DEC_ZERO), output_field=DecimalField()),
                total_purchases=Coalesce(Sum('total_amount', filter=Q(transaction_type='purchase')), Value(DEC_ZERO), output_field=DecimalField()),
                total_returns=Coalesce(Sum('total_amount', filter=Q(transaction_type='return')), Value(DEC_ZERO), output_field=DecimalField()),
                transaction_count=Coalesce(Count('id'), Value(0)),
                total_paid=Coalesce(Sum('paid'), Value(DEC_ZERO), output_field=DecimalField()),
                total_balance=Coalesce(Sum('balance'), Value(DEC_ZERO), output_field=DecimalField()),
                total_quantity=Coalesce(Sum('quantity'), Value(0)),
            )

        # top items
        top_items_qs = DailySaleTransaction.objects.filter(date=date, transaction_type='sale').values(
            'item__id', 'item__name'
        ).annotate(
            total_quantity=Coalesce(Sum('quantity'), Value(0)),
            total_revenue=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField())
        ).order_by('-total_revenue')[:10]

        # recent transactions
        recent_transactions = DailySaleTransaction.objects.filter(date__range=[start_for_trend, date]).select_related(
            'item', 'customer__user', 'container'
        ).order_by('-created_at')[:20]

        # trend (series)
        trend_qs = DailySaleTransaction.objects.filter(date__range=[start_for_trend, date], transaction_type='sale').values('date').annotate(
            daily_sales=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField()),
            daily_count=Coalesce(Count('id'), Value(0))
        ).order_by('date')
        trend = list(trend_qs)

        context = {
            'date': date,
            'daily_stats': daily_stats,
            'top_items': list(top_items_qs),
            'recent_transactions': recent_transactions,
            'trend': trend,
            'days': days,
        }

    except Exception as e:
        logger.exception("admin_dashboard error")
        context = {'error': str(e)}

    return render(request, "daily_sale/dashboard.html", context)


@login_required
def sales_summary_view(request):
    date = _parse_date_param(request.GET.get('date'), timezone.now().date())
    try:
        if REPORTS_AVAILABLE:
            summary = get_sales_summary(date)
        else:
            qs = DailySaleTransaction.objects.filter(date=date, transaction_type='sale')
            total_sales = Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField())
            total_discount = Coalesce(Sum('discount'), Value(DEC_ZERO), output_field=DecimalField())
            total_tax = Coalesce(Sum('tax'), Value(DEC_ZERO), output_field=DecimalField())
            total_paid = Coalesce(Sum('paid'), Value(DEC_ZERO), output_field=DecimalField())
            total_balance = Coalesce(Sum('balance'), Value(DEC_ZERO), output_field=DecimalField())
            ag = qs.aggregate(
                total_sales=total_sales,
                total_discount=total_discount,
                total_tax=total_tax,
                total_paid=total_paid,
                total_balance=total_balance
            )
            summary = {
                'total_sales_amount': ag['total_sales'],
                'total_discount': ag['total_discount'],
                'total_tax': ag['total_tax'],
                'total_paid': ag['total_paid'],
                'total_balance': ag['total_balance'],
            }
        # ensure Decimal objects
        for k, v in summary.items():
            if v is None:
                summary[k] = DEC_ZERO
    except Exception as e:
        logger.exception("sales_summary_view error")
        summary = {
            'total_sales_amount': DEC_ZERO,
            'total_discount': DEC_ZERO,
            'total_tax': DEC_ZERO,
            'total_paid': DEC_ZERO,
            'total_balance': DEC_ZERO,
        }

    context = {'date': date, **summary}
    return render(request, "daily_sale/sales_summary.html", context)


@login_required
def sales_by_item_view(request):
    date = _parse_date_param(request.GET.get('date'), timezone.now().date())
    try:
        if REPORTS_AVAILABLE:
            items = report_sales_by_item(date)
        else:
            qs = DailySaleTransaction.objects.filter(date=date, transaction_type='sale')
            items_qs = qs.values('item__id', 'item__name').annotate(
                total_quantity=Coalesce(Sum('quantity'), Value(0)),
                total_revenue=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField())
            ).order_by('-total_revenue')
            items = list(items_qs)
    except Exception as e:
        logger.exception("sales_by_item_view error")
        items = []

    return render(request, "daily_sale/sales_by_item.html", {'date': date, 'items_sales': items})


@login_required
def outstanding_customers_view(request):
    date = _parse_date_param(request.GET.get('date'), timezone.now().date())
    try:
        if REPORTS_AVAILABLE:
            customers = report_outstanding_customers(date)
        else:
            qs = DailySaleTransaction.objects.filter(date=date, transaction_type='sale', balance__gt=0)
            customers_qs = qs.values('customer__id', 'customer__user__first_name', 'customer__user__last_name').annotate(
                total_outstanding=Coalesce(Sum('balance'), Value(DEC_ZERO), output_field=DecimalField())
            ).order_by('-total_outstanding')
            customers = list(customers_qs)
    except Exception as e:
        logger.exception("outstanding_customers_view error")
        customers = []

    return render(request, "daily_sale/outstanding_customers.html", {'date': date, 'customers': customers})


@login_required
def sales_and_purchases_range_view(request):
    start = _parse_date_param(request.GET.get('start_date'), timezone.now().date())
    end = _parse_date_param(request.GET.get('end_date'), timezone.now().date())
    if start > end:
        start, end = end, start
    try:
        qs = DailySaleTransaction.objects.filter(date__range=[start, end])
        aggs = qs.aggregate(
            total_sales=Coalesce(Sum('total_amount', filter=Q(transaction_type='sale')), Value(DEC_ZERO), output_field=DecimalField()),
            total_purchases=Coalesce(Sum('total_amount', filter=Q(transaction_type='purchase')), Value(DEC_ZERO), output_field=DecimalField()),
        )
    except Exception as e:
        logger.exception("sales_and_purchases_range_view error")
        aggs = {'total_sales': DEC_ZERO, 'total_purchases': DEC_ZERO}

    return render(request, "daily_sale/sales_and_purchases_range.html", {'start_date': start, 'end_date': end, **aggs})


@login_required
def financial_analytics_view(request):
    """
    Advanced financial analytics for a range.
    Returns aggregates and day-by-day trend for charting.
    """
    default_start = timezone.now().date() - timedelta(days=30)
    start = _parse_date_param(request.GET.get('start_date'), default_start)
    end = _parse_date_param(request.GET.get('end_date'), timezone.now().date())
    if start > end:
        start, end = end, start

    try:
        qs = DailySaleTransaction.objects.filter(date__range=[start, end])
        financial_data = qs.aggregate(
            total_revenue=Coalesce(Sum('total_amount', filter=Q(transaction_type='sale')), Value(DEC_ZERO), output_field=DecimalField()),
            total_cost=Coalesce(Sum('total_amount', filter=Q(transaction_type='purchase')), Value(DEC_ZERO), output_field=DecimalField()),
            net_profit=Coalesce(
                Sum(
                    Case(
                        When(transaction_type='sale', then=F('total_amount')),
                        When(transaction_type='purchase', then=F('total_amount') * Value(-1)),
                        default=Value(0),
                        output_field=DecimalField(max_digits=18, decimal_places=2)
                    )
                ),
                Value(DEC_ZERO),
                output_field=DecimalField()
            ),
            total_transactions=Coalesce(Count('id'), Value(0)),
            avg_transaction=Coalesce(Avg('total_amount'), Value(DEC_ZERO), output_field=DecimalField()),
        )

        daily_trend_qs = qs.filter(transaction_type='sale').values('date').annotate(
            daily_sales=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField()),
            daily_count=Coalesce(Count('id'), Value(0))
        ).order_by('date')
        daily_trend = list(daily_trend_qs)
    except Exception as e:
        logger.exception("financial_analytics_view error")
        financial_data = {}
        daily_trend = []

    return render(request, "daily_sale/financial_analytics.html", {
        'start_date': start, 'end_date': end,
        'financial_data': financial_data, 'daily_trend': daily_trend
    })


@login_required
def customer_analysis_view(request):
    date = _parse_date_param(request.GET.get('date'), timezone.now().date())
    try:
        qs = DailySaleTransaction.objects.filter(date=date, transaction_type='sale')
        customer_qs = qs.values('customer__id', 'customer__user__first_name', 'customer__user__last_name').annotate(
            total_purchases=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField()),
            transaction_count=Coalesce(Count('id'), Value(0)),
            avg_purchase=Coalesce(Avg('total_amount'), Value(DEC_ZERO), output_field=DecimalField()),
            last_transaction=Max('created_at')
        ).order_by('-total_purchases')
        customer_analysis = list(customer_qs)
    except Exception as e:
        logger.exception("customer_analysis_view error")
        customer_analysis = []

    return render(request, "daily_sale/customer_analysis.html", {'date': date, 'customer_analysis': customer_analysis})


@login_required
def container_sales_view(request):
    date = _parse_date_param(request.GET.get('date'), timezone.now().date())
    try:
        qs = DailySaleTransaction.objects.filter(date=date, transaction_type='sale')
        container_qs = qs.values('container__id', 'container__name').annotate(
            total_sales=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField()),
            item_count=Coalesce(Count('item', distinct=True), Value(0)),
            transaction_count=Coalesce(Count('id'), Value(0))
        ).order_by('-total_sales')
        container_sales = list(container_qs)
    except Exception as e:
        logger.exception("container_sales_view error")
        container_sales = []

    return render(request, "daily_sale/container_sales.html", {'date': date, 'container_sales': container_sales})


# ----------------------
# JSON APIs for frontend charts / realtime
# ----------------------
@login_required
def real_time_stats_api(request):
    """
    Return today stats as JSON. Decimal values are converted to strings for safe JSON serialization.
    """
    today = timezone.now().date()
    try:
        ag = DailySaleTransaction.objects.filter(date=today).aggregate(
            today_sales=Coalesce(Sum('total_amount', filter=Q(transaction_type='sale')), Value(DEC_ZERO), output_field=DecimalField()),
            today_purchases=Coalesce(Sum('total_amount', filter=Q(transaction_type='purchase')), Value(DEC_ZERO), output_field=DecimalField()),
            today_transactions=Coalesce(Count('id'), Value(0)),
            pending_balance=Coalesce(Sum('balance', filter=Q(status='pending')), Value(DEC_ZERO), output_field=DecimalField())
        )
    except Exception as e:
        logger.exception("real_time_stats_api error")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    # convert Decimal to string
    for k, v in ag.items():
        if isinstance(v, Decimal):
            ag[k] = str(v)
    ag['date'] = str(today)
    ag['status'] = 'success'
    return JsonResponse(ag)


@login_required
def sales_timeseries_api(request):
    """
    Return sales timeseries for last N days. ?days=30
    """
    days = int(request.GET.get('days', 30))
    if days <= 0 or days > 3650:
        return HttpResponseBadRequest("days must be between 1 and 3650")

    end = timezone.now().date()
    start = end - timedelta(days=days - 1)
    try:
        qs = DailySaleTransaction.objects.filter(date__range=[start, end], transaction_type='sale')
        series_qs = qs.values('date').annotate(
            sales=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField()),
            count=Coalesce(Count('id'), Value(0))
        ).order_by('date')
        series = [{'date': r['date'].isoformat(), 'sales': str(r['sales']), 'count': r['count']} for r in series_qs]
    except Exception as e:
        logger.exception("sales_timeseries_api error")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'success', 'series': series})


@login_required
def sales_by_item_api(request):
    """
    Return sales aggregated by item for a date (or date range).
    params: date=YYYY-MM-DD  OR start_date & end_date
    """
    date = request.GET.get('date')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if date:
        date = _parse_date_param(date, None)
        if not date:
            return HttpResponseBadRequest("Invalid date")
        qs = DailySaleTransaction.objects.filter(date=date, transaction_type='sale')
    elif start_date or end_date:
        s = _parse_date_param(start_date, timezone.now().date() - timedelta(days=30))
        e = _parse_date_param(end_date, timezone.now().date())
        if s > e:
            s, e = e, s
        qs = DailySaleTransaction.objects.filter(date__range=[s, e], transaction_type='sale')
    else:
        # default last 30 days
        e = timezone.now().date()
        s = e - timedelta(days=29)
        qs = DailySaleTransaction.objects.filter(date__range=[s, e], transaction_type='sale')

    try:
        res_qs = qs.values('item__id', 'item__name').annotate(
            total_quantity=Coalesce(Sum('quantity'), Value(0)),
            total_revenue=Coalesce(Sum('total_amount'), Value(DEC_ZERO), output_field=DecimalField())
        ).order_by('-total_revenue')[:200]
        res = [{'item_id': r['item__id'], 'item_name': r['item__name'], 'total_quantity': int(r['total_quantity']), 'total_revenue': str(r['total_revenue'])} for r in res_qs]
    except Exception as e:
        logger.exception("sales_by_item_api error")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'success', 'data': res})


# ----------------------
# small convenience views
# ----------------------
@login_required
def dashboard_overview(request):
    """
    Simple redirect or view that shows a compact overview (non-admin).
    Admins should use admin_dashboard view.
    """
    if is_admin_user(request.user):
        return redirect('daily_sale:admin_dashboard')
    # For normal user show their transactions and balances
    today = timezone.now().date()
    user_profile = getattr(request.user, 'userprofile', None)
    user_transactions = DailySaleTransaction.objects.filter(customer=user_profile).order_by('-date')[:50]
    return render(request, "daily_sale/user_dashboard.html", {'transactions': user_transactions, 'today': today})
