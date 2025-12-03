# containers/views.py
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView, TemplateView, View, CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Count
from django.utils import timezone
from datetime import datetime
from .models import Saraf, Container, ContainerTransaction, Inventory_List, SarafTransaction
from . import report
from django.utils.dateparse import parse_date
from django.urls import reverse_lazy
from django import forms
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal


def container_financial_report(request, container_id):
    container = get_object_or_404(Container, id=container_id)
    transactions = container.transactions.all()

    total_income = transactions.filter(
        sale_status__in=["sold_to_company", "sold_to_customer"]
    ).aggregate(total_income=Sum('total_price'))["total_income"] or 0

    total_sold_qty = transactions.aggregate(
        total_sold=Sum('quantity')
    )["total_sold"] or 0

    return render(request, 'container/container_financial_report.html', {
        'container': container,
        'total_income': total_income,
        'total_sold_qty': total_sold_qty,
        'transactions': transactions
    })

def saraf_balance_report(request):
    sarafs = Saraf.objects.annotate(
        total_received=Sum('transactions__received_from_saraf'),
        total_paid=Sum('transactions__paid_by_company'),
        total_debit=Sum('transactions__debit_company'),
    ).annotate(
        balance=F('total_received') + F('total_debit') - F('total_paid')
    )

    return render(request, 'container/saraf_balance_report.html', {'sarafs': sarafs})  # اصلاح typo

# containers/views.py
@login_required
def saraf_transactions_report(request, saraf_id):
    """
    گزارش تراکنش‌های یک صراف خاص
    """
    saraf = get_object_or_404(Saraf, id=saraf_id)
    
    # فیلتر کردن بر اساس تاریخ اگر وجود دارد
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    transactions = saraf.transactions.select_related('container').all()
    
    if start_date:
        transactions = transactions.filter(transaction_time__gte=parse_date(start_date))
    if end_date:
        transactions = transactions.filter(transaction_time__lte=parse_date(end_date))
    
    # محاسبه جمع‌های مالی
    total_received = transactions.aggregate(total=Sum('received_from_saraf'))['total'] or 0
    total_paid = transactions.aggregate(total=Sum('paid_by_company'))['total'] or 0
    total_debit = transactions.aggregate(total=Sum('debit_company'))['total'] or 0
    
    context = {
        'saraf': saraf,
        'transactions': transactions.order_by('-transaction_time'),
        'total_received': total_received,
        'total_paid': total_paid,
        'total_debit': total_debit,
        'net_balance': total_received + total_debit - total_paid,
    }
    
    return render(request, 'container/saraf_transactions_report.html', context)

def total_container_transactions_report(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    transactions = ContainerTransaction.objects.all()

    if start_date:
        transactions = transactions.filter(created_at__gte=parse_date(start_date))
    if end_date:
        transactions = transactions.filter(created_at__lte=parse_date(end_date))

    report = transactions.values(
        'sale_status',
        'transport_status',
        'payment_status'
    ).annotate(
        total_amount=Sum('total_price')
    )

    return render(request, 'container/total_container_transactions_report.html', {
        'report': report
    })


class CompanyAccessMixin:
    """Limit queries by user's company if available on profile"""
    def get_company(self):
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return None
        profile = getattr(user, "profile", None)
        if not profile:
            return None
        return profile.company

# --- Saraf views ---

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
        
        # محاسبات فقط در ویو
        return qs.annotate(
            total_received=Coalesce(Sum("transactions__received_from_saraf"), Decimal('0')),
            total_paid=Coalesce(Sum("transactions__paid_by_company"), Decimal('0')),
        ).annotate(
            balance=F("total_received") - F("total_paid")
        ).order_by("-balance")

class SarafDetailView(LoginRequiredMixin, CompanyAccessMixin, DetailView):
    model = Saraf
    template_name = "container/saraf_detail.html"
    context_object_name = "saraf"
    pk_url_kwarg = "saraf_id"

    def get_queryset(self):
        qs = super().get_queryset().select_related("user")
        company = self.get_company()
        if company:
            qs = qs.filter(user__company=company)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        saraf = self.object
        ctx["transactions"] = saraf.transactions.select_related("container").order_by("-transaction_time")[:200]
        ctx["summary"] = report.saraf_balance_summary()
        return ctx

# --- Container views ---

# containers/views.py
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
        
        # استفاده از نام فیلدهای صحیح بر اساس مدل Container
        qs = qs.annotate(
            products_count=Count('inventory_items', distinct=True),  # اصلاح به inventory_items
            total_in_stock_qty=Sum('inventory_items__in_stock_qty'),
            total_inventory_value=Sum(F('inventory_items__in_stock_qty') * F('inventory_items__unit_price'))
        )
        return qs.order_by('-created_at')

# اضافه کردن view های جدید
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

class ContainerCreateView(LoginRequiredMixin, CompanyAccessMixin, CreateView):
    model = Container
    template_name = "container/container_form.html"
    fields = ['name', 'container_number', 'company', 'description']  # تنظیم فیلدهای مورد نیاز
    success_url = reverse_lazy("container:list")

    def form_valid(self, form):
        # اگر کاربر متعلق به شرکت است، به صورت خودکار شرکت را تنظیم کنید
        company = self.get_company()
        if company:
            form.instance.company = company
        return super().form_valid(form)

@login_required
def container_financial_report_view(request, container_id):
    """
    Page: Container financial summary and list of transactions.
    GET params: start_date, end_date
    """
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
    return render(request, "container/total_container_transactions_report.html", {"report": data})

# quick admin overview (dashboard widget)
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