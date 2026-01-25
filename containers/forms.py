from django import forms
from django.utils import timezone
from decimal import Decimal
from django.db.models import Sum, Count, Max, Min, Avg
from django.db.models.functions import Coalesce
from .models import Saraf, Container, SarafTransaction
import json
from django.db.models.functions import TruncMonth

class SarafPaymentWithReportForm(forms.ModelForm):
    class Meta:
        model = SarafTransaction
        fields = [
            'saraf', 'container', 'received_from_saraf', 'paid_by_company', 
            'currency', 'description'
        ]
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'description',
                'class': 'form-control'
            }),
            'received_from_saraf': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '1',
                'min': '0',
                'placeholder': 'received_from_saraf'
            }),
            'paid_by_company': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '1',
                'min': '0',
                'placeholder': 'paid_by_company'
            }),
            'saraf': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_saraf_select'
            }),
            'container': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_container_select'
            }),
            'currency': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_currency_select'
            }),
        }
        labels = {
            'received_from_saraf': 'received_from_saraf',
            'paid_by_company': 'paid_by_company',
            'description': 'description',
            'saraf': 'saraf',
            'container': 'container',
            'currency': 'currency',
        }

    def __init__(self, *args, **kwargs):
        self.company = kwargs.pop('company', None)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        if self.company:
            self.fields['saraf'].queryset = Saraf.objects.filter(
                user__company=self.company,
                is_active=True,
                user__is_active=True
            ).select_related('user').order_by('user__first_name')
        else:
            self.fields['saraf'].queryset = Saraf.objects.filter(
                is_active=True,
                user__is_active=True
            ).select_related('user').order_by('user__first_name')

        if self.company:
            self.fields['container'].queryset = Container.objects.filter(
                company=self.company
            ).order_by('-created_at')
        else:
            self.fields['container'].queryset = Container.objects.all().order_by('-created_at')

        self.fields['financial_report'] = forms.CharField(
            required=False,
            widget=forms.HiddenInput()
        )

        self.fields['current_balance'] = forms.DecimalField(
            required=False,
            widget=forms.NumberInput(attrs={
                'class': 'form-control',
                'readonly': True,
                'style': 'background-color: #f8f9fa; font-weight: bold;'
            }),
            label='balance'
        )
        
        self.fields['new_balance'] = forms.DecimalField(
            required=False,
            widget=forms.NumberInput(attrs={
                'class': 'form-control',
                'readonly': True,
                'style': 'background-color: #f8f9fa; font-weight: bold;'
            }),
            label='new balance'
        )

    def clean(self):
        cleaned_data = super().clean()
        saraf = cleaned_data.get('saraf')
        currency = cleaned_data.get('currency', 'usd')
        received = cleaned_data.get('received_from_saraf', Decimal('0'))
        paid = cleaned_data.get('paid_by_company', Decimal('0'))
        
        if saraf:

            report = self.calculate_financial_report(saraf, currency)
            cleaned_data['financial_report'] = json.dumps(report, default=str)

            current_balance = report['current_balance']
            new_balance = current_balance + received - paid
            
            cleaned_data['current_balance'] = current_balance
            cleaned_data['new_balance'] = new_balance

            if new_balance < Decimal('-1000000'):
                self.add_error(None, 
                    f'${new_balance:,.0f}.')

        if received == Decimal('0') and paid == Decimal('0'):
            self.add_error(None, 'at least one field must fill!')
        
        return cleaned_data

    def calculate_financial_report(self, saraf, currency):
        transactions = SarafTransaction.objects.filter(
            saraf=saraf,
            currency=currency
        ).select_related('container')

        transaction_stats = transactions.aggregate(
            total_received=Coalesce(Sum('received_from_saraf'), Decimal('0')),
            total_paid=Coalesce(Sum('paid_by_company'), Decimal('0')),
            count=Count('id'),
            max_received=Coalesce(Max('received_from_saraf'), Decimal('0')),
            max_paid=Coalesce(Max('paid_by_company'), Decimal('0')),
            avg_received=Coalesce(Avg('received_from_saraf'), Decimal('0')),
            avg_paid=Coalesce(Avg('paid_by_company'), Decimal('0')),
            first_transaction=Min('transaction_time'),
            last_transaction=Max('transaction_time')
        )

        current_balance = transaction_stats['total_received'] - transaction_stats['total_paid']
        recent_transactions = transactions.order_by('-transaction_time')[:10]
        recent_data = []
        for tx in recent_transactions:
            recent_data.append({
                'date': tx.transaction_time.strftime('%Y-%m-%d %H:%M'),
                'received': float(tx.received_from_saraf),
                'paid': float(tx.paid_by_company),
                'balance': float(tx.balance) if tx.balance else 0,
                'container': str(tx.container) if tx.container else '',
                'description': tx.description
            })

        monthly_stats = self.get_monthly_stats(saraf, currency)

        containers = Container.objects.filter(
            Saraf_transactions__saraf=saraf
        ).distinct().annotate(
            total_received=Coalesce(Sum('Saraf_transactions__received_from_saraf', 
                filter=Container.Q(Saraf_transactions__currency=currency)), Decimal('0')),
            total_paid=Coalesce(Sum('Saraf_transactions__paid_by_company',
                filter=Container.Q(Saraf_transactions__currency=currency)), Decimal('0'))
        )
        
        container_data = []
        for container in containers:
            if container.total_received > 0 or container.total_paid > 0:
                container_data.append({
                    'number': container.container_number,
                    'name': container.name,
                    'received': float(container.total_received),
                    'paid': float(container.total_paid),
                    'balance': float(container.total_received - container.total_paid)
                })

        report = {
            'saraf_name': str(saraf.user.full_name if saraf.user and saraf.user.full_name else 
                saraf.user.username if saraf.user else 'Unknown'),
            'saraf_id': str(saraf.id),
            'currency': currency,
            'current_balance': float(current_balance),
            'total_received': float(transaction_stats['total_received']),
            'total_paid': float(transaction_stats['total_paid']),
            'transaction_count': transaction_stats['count'],
            'avg_received': float(transaction_stats['avg_received']),
            'avg_paid': float(transaction_stats['avg_paid']),
            'max_received': float(transaction_stats['max_received']),
            'max_paid': float(transaction_stats['max_paid']),
            'first_transaction': transaction_stats['first_transaction'].strftime('%Y-%m-%d') if transaction_stats['first_transaction'] else None,
            'last_transaction': transaction_stats['last_transaction'].strftime('%Y-%m-%d %H:%M') if transaction_stats['last_transaction'] else None,
            'recent_transactions': recent_data,
            'monthly_stats': monthly_stats,
            'containers': container_data,
        }
        
        return report

    def get_monthly_stats(self, saraf, currency):
        
        monthly = SarafTransaction.objects.filter(
            saraf=saraf,
            currency=currency
        ).annotate(
            month=TruncMonth('transaction_time')
        ).values('month').annotate(
            received=Coalesce(Sum('received_from_saraf'), Decimal('0')),
            paid=Coalesce(Sum('paid_by_company'), Decimal('0')),
            count=Count('id')
        ).order_by('-month')
        
        monthly_data = []
        for month in monthly[:12]:
            monthly_data.append({
                'month': month['month'].strftime('%Y-%m'),
                'received': float(month['received']),
                'paid': float(month['paid']),
                'balance': float(month['received'] - month['paid']),
                'count': month['count']
            })
        
        return monthly_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        report = json.loads(self.cleaned_data.get('financial_report', '{}'))
        current_balance = Decimal(str(report.get('current_balance', 0)))
        received = self.cleaned_data.get('received_from_saraf', Decimal('0'))
        paid = self.cleaned_data.get('paid_by_company', Decimal('0'))
        
        instance.balance = current_balance + received - paid
        instance.transaction_time = timezone.now()
        
        if commit:
            instance.save()
        
        return instance