# containers/views.py
from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView, TemplateView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Count
from django.utils import timezone
from datetime import datetime
from .models import Saraf, Container, ContainerTransaction, Inventory_List, SarafTransaction
from . import report
from django.utils.dateparse import parse_date
from django.views.generic import CreateView
from django.urls import reverse_lazy
from django import forms


def container_financial_report(request, container_id):
    container = get_object_or_404(Container, id=container_id)
    transactions = container.transactions.all()

    total_income = transactions.filter(
        sale_status__in=["sold_to_company", "sold_to_customer"]
    ).aggregate(total_income=Sum('total_price'))["total_income"] or 0

    total_sold_qty = transactions.aggregate(
        total_sold=Sum('quantity')
    )["total_sold"] or 0

    return render(request, 'containers/container_financial_report.html', {
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

    return render(request, 'contaoners/saraf_balance_report.html', {'sarafs': sarafs})

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

    return render(request, 'containers/container_transactions_report.html', {
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
    template_name = "containers/saraf_list.html"
    context_object_name = "sarafs"
    paginate_by = 25

    def get_queryset(self):
        qs = Saraf.objects.select_related("user")
        company = self.get_company()
        if company:
            qs = qs.filter(user__company=company)
        # annotate balances (DB-side) using report utility
        return qs.annotate(
            total_received=Sum("transactions__received_from_saraf"),
            total_paid=Sum("transactions__paid_by_company"),
            total_debit=Sum("transactions__debit_company"),
        ).annotate(balance=F("total_received") + F("total_debit") - F("total_paid")).order_by("-balance")

class SarafDetailView(LoginRequiredMixin, CompanyAccessMixin, DetailView):
    model = Saraf
    template_name = "containers/saraf_detail.html"
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
        ctx["summary"] = report.saraf_balance_summary()  # can be narrowed by company if needed
        return ctx

# --- Container views ---

class ContainerListView(LoginRequiredMixin, CompanyAccessMixin, ListView):
    model = Container
    template_name = "containers/container_list.html"
    context_object_name = "containers"
    paginate_by = 25
    
    def get_queryset(self):
        qs = Container.objects.select_related("company")
        company = self.get_company()
        if company:
            qs = qs.filter(company=company)
        qs = qs.annotate(
            products_count=Count('Inventory_container', distinct=True),
            total_in_stock_qty=Sum('Inventory_container__in_stock_qty'),
            total_inventory_value=Sum(F('Inventory_container__in_stock_qty') * F('Inventory_container__unit_price'))
    )
        return qs.order_by('-created_at')

    def get_queryset(self):
        qs = Container.objects.select_related("company")
        company = self.get_company()
        if company:
            qs = qs.filter(company=company)
        # annotate with aggregated inventory value & product count
        qs = qs.annotate(
            product_count=Sum("Inventory_container__in_stock_qty")  # NOTE: alternative is to use report.container_inventory_summary
        )
        return qs.order_by("-created_at")

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
        start_parsed = datetime.fromisoformat(start)
    else:
        start_parsed = None
    if end:
        end_parsed = datetime.fromisoformat(end)
    else:
        end_parsed = None

    fin = report.container_financial_summary(container_id=container_id, start_date=start_parsed, end_date=end_parsed)
    transactions = container.transactions.select_related("customer", "company").order_by("-created_at")

    context = {
        "container": container,
        "financial_summary": fin,
        "transactions": transactions,
    }
    return render(request, "containers/container_financial_report.html", context)


@login_required
def total_container_transactions_report_view(request):
    company = getattr(request.user.profile, "company", None)
    start = request.GET.get("start_date")
    end = request.GET.get("end_date")
    data = report.total_container_transactions_report(company_id=(company.id if company else None), start_date=start, end_date=end)
    return render(request, "containers/total_container_transactions_report.html", {"report": data})

# quick admin overview (dashboard widget)
class ContainersAdminOverview(LoginRequiredMixin, TemplateView, CompanyAccessMixin):
    template_name = "containers/admin_overview.html"

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
    template_name = "containers/inventory_add.html"
    success_url = reverse_lazy("containers:container_list")

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        # restrict containers to user's company if available
        company = getattr(self.request.user.profile, "company", None)
        if company:
            form.fields["container"].queryset = Container.objects.filter(company=company)
        else:
            form.fields["container"].queryset = Container.objects.all()
        return form