# containers/views.py
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView, TemplateView,  CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Count, DecimalField, Max, Min, Avg
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Saraf, Container, Inventory_List
from . import report
from django.urls import reverse_lazy
from django import forms
from django.db.models.functions import Coalesce
from decimal import Decimal
from collections import defaultdict

class CompanyAccessMixin:
    def get_company(self):
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return None
        profile = getattr(user, "profile", None)
        if not profile:
            return None
        return profile.company

class SarafListView(LoginRequiredMixin, CompanyAccessMixin, ListView):
    model = Saraf
    template_name = "container/saraf_list.html"
    context_object_name = "sarafs"
    paginate_by = 25

    def get_queryset(self):
        qs = Saraf.objects.select_related("user")
        company = self.get_company()
        
        if company:
            qs = qs.filter(user__company=company)
        return qs.annotate(
            total_received=Coalesce(
                Sum("transactions__received_from_saraf"), 
                Decimal('0'),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
            total_paid=Coalesce(
                Sum("transactions__paid_by_company"), 
                Decimal('0'),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            ),
        ).annotate(
            balance=F("total_received") - F("total_paid")
        ).order_by("-balance")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sarafs = context['sarafs']
        all_sarafs = self.get_queryset()
        
        total_received_sum = all_sarafs.aggregate(
            total=Coalesce(Sum('total_received'), Decimal('0'))
        )['total']
        
        total_paid_sum = all_sarafs.aggregate(
            total=Coalesce(Sum('total_paid'), Decimal('0'))
        )['total']
        
        net_balance_sum = total_received_sum - total_paid_sum
        creditors_count = all_sarafs.filter(balance__gt=0).count()
        debtors_count = all_sarafs.filter(balance__lt=0).count()
        balanced_count = all_sarafs.filter(balance=0).count()
        context.update({
            'total_received_sum': total_received_sum,
            'total_paid_sum': total_paid_sum,
            'net_balance_sum': net_balance_sum,
            'creditors_count': creditors_count,
            'debtors_count': debtors_count,
            'balanced_count': balanced_count,
            'total_count': all_sarafs.count(),
            'page_title': 'Sarafs Management',
            'page_subtitle': 'Financial accounts overview',
        })
        
        return context

class SarafDetailView(LoginRequiredMixin, CompanyAccessMixin, DetailView):
    model = Saraf
    template_name = "container/saraf_detail.html"
    context_object_name = "saraf"
    pk_url_kwarg = "saraf_id"

    def get_queryset(self):
        qs = super().get_queryset().select_related(
            "user",
            "user__user",
            "user__company"
        )
        company = self.get_company()
        if company:
            qs = qs.filter(user__company=company)
        return qs

    def get_transaction_summary(self, saraf):
        transactions = saraf.transactions.all()
        summary = transactions.aggregate(
            total_received=Coalesce(Sum('received_from_saraf'), Decimal('0')),
            total_paid=Coalesce(Sum('paid_by_company'), Decimal('0')),
            avg_received=Coalesce(Avg('received_from_saraf'), Decimal('0')),
            avg_paid=Coalesce(Avg('paid_by_company'), Decimal('0')),
            max_received=Coalesce(Max('received_from_saraf'), Decimal('0')),
            max_paid=Coalesce(Max('paid_by_company'), Decimal('0')),
            transaction_count=Count('id'),
            first_transaction=Min('transaction_time'),
            last_transaction=Max('transaction_time')
        )
        summary['balance'] = summary['total_received'] - summary['total_paid']
        
        return summary

    def get_currency_breakdown(self, saraf):
        transactions = saraf.transactions.all()
        currency_data = {}
        for currency in ['usd', 'eur', 'aed']:
            currency_trans = transactions.filter(currency=currency)
            
            if currency_trans.exists():
                stats = currency_trans.aggregate(
                    total_received=Coalesce(Sum('received_from_saraf'), Decimal('0')),
                    total_paid=Coalesce(Sum('paid_by_company'), Decimal('0')),
                    count=Count('id'),
                    avg_amount=Coalesce(Avg('received_from_saraf'), Decimal('0'))
                )
                
                stats['balance'] = stats['total_received'] - stats['total_paid']
        return currency_data

    def get_monthly_summary(self, saraf):
        current_year = timezone.now().year
        transactions = saraf.transactions.filter(
            transaction_time__year=current_year
        )
        
        monthly_data = []
        for month in range(1, 13):
            month_trans = transactions.filter(
                transaction_time__month=month
            )
            
            month_stats = month_trans.aggregate(
                received=Coalesce(Sum('received_from_saraf'), Decimal('0')),
                paid=Coalesce(Sum('paid_by_company'), Decimal('0')),
                count=Count('id')
            )
            
            month_stats['balance'] = month_stats['received'] - month_stats['paid']
            month_stats['month_name'] = timezone.datetime(current_year, month, 1).strftime('%b')
            monthly_data.append(month_stats)
        return monthly_data

    def get_container_summary(self, saraf):
        transactions = saraf.transactions.filter(
            container__isnull=False
        ).select_related('container')
        
        containers = defaultdict(lambda: {
            'received': Decimal('0'),
            'paid': Decimal('0'),
            'count': 0,
            'last_transaction': None
        })
        
        for tx in transactions:
            container = tx.container
            if container:
                containers[container.id]['container'] = container
                containers[container.id]['received'] += tx.received_from_saraf
                containers[container.id]['paid'] += tx.paid_by_company
                containers[container.id]['count'] += 1
                containers[container.id]['balance'] = containers[container.id]['received'] - containers[container.id]['paid']
                
                if not containers[container.id]['last_transaction'] or \
                   tx.transaction_time > containers[container.id]['last_transaction']:
                    containers[container.id]['last_transaction'] = tx.transaction_time
        
        return list(containers.values())

    def get_recent_activity(self, saraf, days=30):
        cutoff_date = timezone.now() - timedelta(days=days)
        return saraf.transactions.filter(
            transaction_time__gte=cutoff_date
        ).select_related('container').order_by('-transaction_time')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        saraf = self.object
        date_filter = self.request.GET.get('date_filter', 'all')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')
        transactions = saraf.transactions.select_related("container").all()
        
        if date_filter == 'today':
            today = timezone.now().date()
            transactions = transactions.filter(transaction_time__date=today)
        elif date_filter == 'week':
            week_ago = timezone.now() - timedelta(days=7)
            transactions = transactions.filter(transaction_time__gte=week_ago)
        elif date_filter == 'month':
            month_ago = timezone.now() - timedelta(days=30)
            transactions = transactions.filter(transaction_time__gte=month_ago)
        elif date_filter == 'year':
            year_ago = timezone.now() - timedelta(days=365)
            transactions = transactions.filter(transaction_time__gte=year_ago)
        elif start_date and end_date:
            transactions = transactions.filter(
                transaction_time__date__range=[start_date, end_date]
            )
        financial_summary = self.get_transaction_summary(saraf)
        monthly_summary = self.get_monthly_summary(saraf)
        container_summary = self.get_container_summary(saraf)
        recent_activity = self.get_recent_activity(saraf, 30)
        user_info = {}
        if saraf.user:
            user_info = {
                'full_name': saraf.user.full_name,
                'phone': saraf.user.phone,
                'email': saraf.user.email,
                'address': saraf.user.address,
                'national_id': saraf.user.national_id,
                'company_name': saraf.user.company_name if saraf.user.company else None,
                'date_joined': saraf.user.user.date_joined if saraf.user.user else None,
                'last_login': saraf.user.user.last_login if saraf.user.user else None,
            }

        status_info = {
            'is_active': saraf.is_active,
            'created_at': saraf.created_at,
            'updated_at': saraf.updated_at,
            'status': 'Creditor' if financial_summary['balance'] > 0 else \
                'Debtor' if financial_summary['balance'] < 0 else 'Balanced',
            'status_class': 'success' if financial_summary['balance'] > 0 else \
                'danger' if financial_summary['balance'] < 0 else 'secondary'
        }
        ctx.update({
            'transactions': transactions.order_by('-transaction_time')[:100],
            'total_transactions_count': transactions.count(),
            'financial_summary': financial_summary,
            'monthly_summary': monthly_summary,
            'container_summary': container_summary[:10],
            'recent_activity': recent_activity[:20],
            'user_info': user_info,
            'status_info': status_info,
            'date_filter': date_filter,
            'start_date': start_date,
            'end_date': end_date,
            'today': timezone.now().date(),
            'page_title': f'Saraf Details - {user_info.get("full_name", "Unknown")}',
            'page_subtitle': f'ID: {saraf.id} | Balance: ${financial_summary["balance"]:,.0f}',
        })
        
        return ctx

class ContainerListView(LoginRequiredMixin, CompanyAccessMixin, ListView):
    model = Container
    template_name = "container/container_list.html"
    context_object_name = "containers"
    paginate_by = 25
    
    def get_queryset(self):
        qs = Container.objects.select_related("company")
        company = self.get_company()
        if company:
            qs = qs.filter(company=company)
        qs = qs.annotate(
            products_count=Count('inventory_items', distinct=True), 
            total_in_stock_qty=Sum('inventory_items__in_stock_qty'),
            total_inventory_value=Sum(F('inventory_items__in_stock_qty') * F('inventory_items__unit_price'))
        )
        return qs.order_by('-created_at')
 
class ContainerDetailView(LoginRequiredMixin, CompanyAccessMixin, DetailView):
    model = Container
    template_name = "container/container_detail.html"
    context_object_name = "container"

    def get_queryset(self):
        qs = Container.objects.select_related("company")
        company = self.get_company()
        if company:
            qs = qs.filter(company=company)
        return qs
    
@login_required
def container_financial_report_view(request, container_id):
    container = get_object_or_404(Container, id=container_id)
    start = request.GET.get("start_date")
    end = request.GET.get("end_date")
    
    if start:
        try:
            start_parsed = datetime.fromisoformat(start)
        except ValueError:
            start_parsed = None
    else:
        start_parsed = None
    if end:
        try:
            end_parsed = datetime.fromisoformat(end)
        except ValueError:
            end_parsed = None
    else:
        end_parsed = None

    fin = report.container_financial_summary(container_id=container_id, start_date=start_parsed, end_date=end_parsed)
    transactions = container.transactions.select_related("customer", "company").order_by("-created_at")

    context = {
        "container": container,
        "financial_summary": fin,
        "transactions": transactions,
    }
    return render(request, "container/container_financial_report.html", context)


@login_required
def total_container_transactions_report_view(request):
    company = getattr(request.user.profile, "company", None)
    start = request.GET.get("start_date")
    end = request.GET.get("end_date")
    data = report.total_container_transactions_report(company_id=(company.id if company else None), start_date=start, end_date=end)
    return render(request, "container/container_transactions_report.html", {"report": data})


class ContainersAdminOverview(LoginRequiredMixin, TemplateView, CompanyAccessMixin):
    template_name = "container/admin_overview.html"

    def dispatch(self, request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return render(request, "403.html", status=403)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        company = self.get_company()
        ctx.update(report.saraf_overview_for_admin(company_id=(company.id if company else None)))
        return ctx

class InventoryCreateForm(forms.ModelForm):
    class Meta:
        model = Inventory_List
        fields = ["container", "code", "product_name", "make", "model", "in_stock_qty", "unit_price", "price", "description"]

class InventoryCreateView(LoginRequiredMixin, CreateView):
    model = Inventory_List
    form_class = InventoryCreateForm
    template_name = "container/inventory_add.html"
    success_url = reverse_lazy("containers:list")

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        company = getattr(self.request.user.profile, "company", None)
        if company:
            form.fields["container"].queryset = Container.objects.filter(company=company)
        else:
            form.fields["container"].queryset = Container.objects.all()
        return form