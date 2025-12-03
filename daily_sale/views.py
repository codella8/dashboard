from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.core.paginator import Paginator
from django.utils import timezone
from decimal import Decimal

from .models import DailySaleTransaction
from .forms import DailySaleTransactionForm
from .report import (
    get_sales_summary, sales_timeseries, old_transactions,
    parse_date_param
)

# --- UI views ---------------------------------------------------------
@login_required
def dashboard(request):
    today = timezone.now().date()
    today_perf = get_sales_summary(start_date=today, end_date=today)
    recent = DailySaleTransaction.objects.select_related('item','customer','company','container').order_by('-created_at')[:10]
    outstanding = old_transactions()[:10]
    context = {
        'today': today,
        'today_perf': today_perf,
        'recent_transactions': recent,
        'outstanding_list': outstanding,
    }
    return render(request, 'daily_sale/dashboard.html', context)


@login_required
def transaction_create(request):
    if request.method == 'POST':
        form = DailySaleTransactionForm(request.POST, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            comp = form.cleaned_data.get('_computed', {})
            if comp:
                obj.subtotal = comp.get('subtotal', Decimal('0.00'))
                obj.total_amount = comp.get('total_amount', Decimal('0.00'))
                obj.balance = comp.get('balance', Decimal('0.00'))
            obj.save()
            messages.success(request, "Transaction created.")
            return redirect(reverse('daily_sale:dashboard'))
        else:
            messages.error(request, "Fix form errors.")
    else:
        form = DailySaleTransactionForm(user=request.user, initial={'date': timezone.now().date()})
    return render(request, 'daily_sale/transaction_create.html', {'form': form})


@login_required
def transaction_edit(request, pk):
    obj = get_object_or_404(DailySaleTransaction, pk=pk)
    if request.method == 'POST':
        form = DailySaleTransactionForm(request.POST, instance=obj, user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            comp = form.cleaned_data.get('_computed', {})
            if comp:
                obj.subtotal = comp.get('subtotal', Decimal('0.00'))
                obj.total_amount = comp.get('total_amount', Decimal('0.00'))
                obj.balance = comp.get('balance', Decimal('0.00'))
            obj.save()
            messages.success(request, "Transaction updated.")
            return redirect(reverse('daily_sale:transaction_list'))
    else:
        form = DailySaleTransactionForm(instance=obj, user=request.user)
    return render(request, 'daily_sale/transaction_edit.html', {'form': form, 'obj': obj})


@login_required
def transaction_list(request):
    qs = DailySaleTransaction.objects.select_related('item','customer','company','container').order_by('-date','-created_at')
    # simple filters
    start_date = parse_date_param(request.GET.get('start_date'))
    end_date = parse_date_param(request.GET.get('end_date'))
    if start_date:
        qs = qs.filter(date__gte=start_date)
    if end_date:
        qs = qs.filter(date__lte=end_date)
    paginator = Paginator(qs, 25)
    page = request.GET.get('page') or 1
    page_obj = paginator.get_page(page)
    return render(request, 'daily_sale/transaction_list.html', {'page_obj': page_obj, 'start_date': start_date, 'end_date': end_date})


@login_required
def daily_summary(request):
    start_date = parse_date_param(request.GET.get('start_date'))
    end_date = parse_date_param(request.GET.get('end_date'))
    if not start_date and not end_date:
        start_date = timezone.now().date()
        end_date = start_date
    elif start_date and not end_date:
        end_date = start_date
    elif end_date and not start_date:
        start_date = end_date

    series = sales_timeseries(start_date, end_date, group_by='day')
    period = get_sales_summary(start_date, end_date)
    return render(request, 'daily_sale/daily_summary.html', {'daily_series': series, 'period_summary': period, 'start_date': start_date, 'end_date': end_date})


@login_required
def old_transactions_view(request):
    start_date = parse_date_param(request.GET.get('start_date'))
    end_date = parse_date_param(request.GET.get('end_date'))
    results = old_transactions(start_date, end_date)
    paginator = Paginator(results, 25)
    page_obj = paginator.get_page(request.GET.get('page') or 1)
    return render(request, 'daily_sale/old_transactions.html', {'page_obj': page_obj, 'start_date': start_date, 'end_date': end_date})

# --- AJAX endpoints for Select2 search ---------------------------------
@login_required
def ajax_search_containers(request):
    q = request.GET.get('q','').strip()
    limit = int(request.GET.get('limit') or 25)
    from containers.models import Container
    qs = Container.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)  # adjust field name accordingly
    results = [{'id': c.pk, 'text': getattr(c,'name', str(c))} for c in qs.order_by('name')[:limit]]
    return JsonResponse({'results': results})

@login_required
def ajax_search_items(request):
    q = request.GET.get('q','').strip()
    limit = int(request.GET.get('limit') or 25)
    from containers.models import Inventory_List
    qs = Inventory_List.objects.all()
    if q:
        # adjust product name field name if different
        qs = qs.filter(product_name__icontains=q)
    results = [{'id': i.pk, 'text': getattr(i,'product_name', str(i))} for i in qs.order_by('product_name')[:limit]]
    return JsonResponse({'results': results})

@login_required
def ajax_search_companies(request):
    q = request.GET.get('q','').strip()
    limit = int(request.GET.get('limit') or 25)
    from accounts.models import Company
    qs = Company.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)
    results = [{'id': c.pk, 'text': getattr(c,'name', str(c))} for c in qs.order_by('name')[:limit]]
    return JsonResponse({'results': results})

@login_required
def ajax_search_customers(request):
    q = request.GET.get('q','').strip()
    limit = int(request.GET.get('limit') or 25)
    from accounts.models import UserProfile
    qs = UserProfile.objects.select_related('user').all()
    if q:
        qs = qs.filter(Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(user__email__icontains=q) | Q(phone__icontains=q))
    results = []
    for u in qs.order_by('user__first_name')[:limit]:
        label = getattr(u,'display_name', None) or (u.user.get_full_name() if getattr(u,'user',None) else str(u))
        results.append({'id': u.pk, 'text': label})
    return JsonResponse({'results': results})
