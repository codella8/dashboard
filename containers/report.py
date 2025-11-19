from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from datetime import datetime
from .models import Container, ContainerTransaction, Inventory_List, Saraf

def container_inventory_summary(company_id=None):
    """
    Returns per-container inventory summary:
      container_id, container_number, products_count, total_in_stock_qty, total_inventory_value
    """
    qs = Container.objects.all()
    if company_id:
        qs = qs.filter(company_id=company_id)

    qs = qs.annotate(
        products_count=Count('Inventory_container'),
        total_in_stock_qty=Sum('Inventory_container__in_stock_qty'),
        total_inventory_value=Sum(F('Inventory_container__in_stock_qty') * F('Inventory_container__unit_price'))
    ).values(
        'id', 'container_number', 'products_count', 'total_in_stock_qty', 'total_inventory_value'
    )
    return qs

def container_financial_summary(container_id=None, company_id=None, start_date=None, end_date=None):
    """
    Returns aggregated financial summary for a container (or company if container_id None).
    """
    tx_qs = ContainerTransaction.objects.all()
    if container_id:
        tx_qs = tx_qs.filter(container_id=container_id)
    if company_id:
        tx_qs = tx_qs.filter(company_id=company_id)
    if start_date:
        tx_qs = tx_qs.filter(created_at__gte=start_date)
    if end_date:
        tx_qs = tx_qs.filter(created_at__lte=end_date)

    summary = tx_qs.aggregate(
        total_income=Sum('total_price', filter=Q(sale_status__in=['sold_to_company', 'sold_to_customer'])),
        total_transactions=Count('id'),
        total_sold_qty=Sum('quantity')
    )
    return summary

def saraf_balance_summary(company_id=None):
    """
    Return per-saraf totals and balances.
    """
    qs = Saraf.objects.all()
    if company_id:
        qs = qs.filter(user__company_id=company_id)

    qs = qs.annotate(
        total_received=Sum('transactions__received_from_saraf'),
        total_paid=Sum('transactions__paid_by_company'),
        total_debit=Sum('transactions__debit_company'),
    ).annotate(balance=F('total_received') + F('total_debit') - F('total_paid'))
    return qs

def total_container_transactions_report(company_id=None, start_date=None, end_date=None):
    tx_qs = ContainerTransaction.objects.all()
    if company_id:
        tx_qs = tx_qs.filter(company_id=company_id)
    if start_date:
        tx_qs = tx_qs.filter(created_at__gte=start_date)
    if end_date:
        tx_qs = tx_qs.filter(created_at__lte=end_date)

    return tx_qs.values('sale_status', 'transport_status', 'payment_status').annotate(total_amount=Sum('total_price')).order_by('-total_amount')

def saraf_overview_for_admin(company_id=None):
    """
    Return small dict for admin dashboard: total sarafs, total outstanding balances, top 5 debtors
    """
    qs = saraf_balance_summary(company_id=company_id)
    total_sarafs = qs.count()
    total_outstanding = qs.aggregate(total_out=Sum('balance'))['total_out'] or 0
    top_debtors = qs.order_by('-balance')[:5]
    return {
        'total_sarafs': total_sarafs,
        'total_saraf_outstanding': total_outstanding,
        'top_debtors': top_debtors
    }
