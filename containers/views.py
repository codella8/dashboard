from django.shortcuts import render
from .models import Saraf, Container, ContainerTransaction
from django.db.models import Sum, F
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from django.utils.dateparse import parse_date

def saraf_list(request):
    sarafs = Saraf.objects.annotate(
        total_received=Sum('transactions__received_from_saraf'),
        total_paid=Sum('transactions__paid_by_company'),
        total_debit=Sum('transactions__debit_company'),
    ).annotate(
        balance=F('total_received') + F('total_debit') - F('total_paid')
    ).all()

    return render(request, 'saraf_list.html', {'sarafs': sarafs})

def saraf_balance_report(request):
    sarafs = Saraf.objects.annotate(
        total_received=Sum('transactions__received_from_saraf'),
        total_paid=Sum('transactions__paid_by_company'),
        total_debit=Sum('transactions__debit_company'),
    ).annotate(
        balance=F('total_received') + F('total_debit') - F('total_paid')
    ).values('user', 'total_received', 'total_paid', 'total_debit', 'balance')

    return render(request, 'saraf_balance_report.html', {'sarafs': sarafs})

def saraf_detail(request, saraf_id):
    saraf = get_object_or_404(Saraf, id=saraf_id)
    transactions = saraf.transactions.all()

    return render(request, 'saraf_detail.html', {
        'saraf': saraf,
        'transactions': transactions
    })
    
def saraf_transactions_list(request, saraf_id):
    saraf = get_object_or_404(Saraf, id=saraf_id)
    transactions = saraf.transactions.all()

    return render(request, 'saraf_transactions_list.html', {'saraf': saraf, 'transactions': transactions})

def saraf_transactions_report(request, saraf_id):
    saraf = get_object_or_404(Saraf, id=saraf_id)
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    currency = request.GET.get('currency')

    transactions = saraf.transactions.all()

    if start_date:
        transactions = transactions.filter(transaction_time__gte=parse_date(start_date))
    if end_date:
        transactions = transactions.filter(transaction_time__lte=parse_date(end_date))
    if currency:
        transactions = transactions.filter(currency=currency)

    total_received = transactions.aggregate(Sum('received_from_saraf'))['received_from_saraf__sum'] or 0
    total_paid = transactions.aggregate(Sum('paid_by_company'))['paid_by_company__sum'] or 0
    total_balance = total_received - total_paid

    return render(request, 'saraf_transactions_report.html', {
        'saraf': saraf,
        'transactions': transactions,
        'total_received': total_received,
        'total_paid': total_paid,
        'total_balance': total_balance,
    })
    
#کانتینر ها

def container_list(request):
    containers = Container.objects.all()
    return render(request, 'container_list.html', {'containers': containers})

def container_financial_report(request, container_id):
    container = get_object_or_404(Container, id=container_id)
    transactions = container.transactions.all()

    total_price = transactions.aggregate(Sum('total_price'))['total_price__sum'] or 0

    return render(request, 'container_financial_report.html', {
        'container': container,
        'transactions': transactions,
        'total_price': total_price,
    })

def total_container_transactions_report(request):
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    transactions = ContainerTransaction.objects.all()

    if start_date:
        transactions = transactions.filter(created_at__gte=parse_date(start_date))
    if end_date:
        transactions = transactions.filter(created_at__lte=parse_date(end_date))

    report = transactions.values('sale_status', 'transport_status', 'payment_status').annotate(
        total_amount=Sum('total_price')
    )

    return render(request, 'total_container_transactions_report.html', {'report': report})
