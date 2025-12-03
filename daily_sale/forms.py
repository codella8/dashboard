from django import forms
from decimal import Decimal
from .models import DailySaleTransaction
from containers.models import Container, Inventory_List
from accounts.models import UserProfile, Company
from django.utils import timezone

class DailySaleTransactionForm(forms.ModelForm):
    class Meta:
        model = DailySaleTransaction
        fields = [
            'date','transaction_type','company','container','item','quantity','unit_price',
            'discount','tax','advance','currency','status','customer','description','note'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type':'date','class':'form-control'}),
            'transaction_type': forms.Select(attrs={'class':'form-select'}),
            'company': forms.Select(attrs={'class':'form-select select2-ajax', 'data-ajax-url':'ajax_companies'}),
            'container': forms.Select(attrs={'class':'form-select select2-ajax', 'data-ajax-url':'ajax_containers'}),
            'item': forms.Select(attrs={'class':'form-select select2-ajax', 'data-ajax-url':'ajax_items'}),
            'quantity': forms.NumberInput(attrs={'class':'form-control','min':1}),
            'unit_price': forms.NumberInput(attrs={'class':'form-control','step':'0.01'}),
            'discount': forms.NumberInput(attrs={'class':'form-control','step':'0.01'}),
            'tax': forms.NumberInput(attrs={'class':'form-control','step':'0.01'}),
            'advance': forms.NumberInput(attrs={'class':'form-control','step':'0.01'}),
            'currency': forms.Select(attrs={'class':'form-select'}),
            'status': forms.Select(attrs={'class':'form-select'}),
            'customer': forms.Select(attrs={'class':'form-select select2-ajax', 'data-ajax-url':'ajax_customers'}),
            'description': forms.TextInput(attrs={'class':'form-control'}),
            'note': forms.Textarea(attrs={'class':'form-control','rows':3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        # user parameter optional: can be used to restrict company/container results
        super().__init__(*args, **kwargs)
        # set empty queryset to avoid loading huge lists (Select2 will fetch via AJAX)
        self.fields['container'].queryset = Container.objects.none()
        self.fields['item'].queryset = Inventory_List.objects.none()
        self.fields['company'].queryset = Company.objects.none()
        self.fields['customer'].queryset = UserProfile.objects.none()

    def clean(self):
        cleaned = super().clean()
        qty = cleaned.get('quantity') or 0
        unit = cleaned.get('unit_price') or Decimal('0.00')
        discount = cleaned.get('discount') or Decimal('0.00')
        tax = cleaned.get('tax') or Decimal('0.00')
        advance = cleaned.get('advance') or Decimal('0.00')

        subtotal = Decimal(qty) * Decimal(unit)
        total = subtotal - Decimal(discount) + Decimal(tax)
        balance = total - Decimal(advance)

        cleaned['_computed'] = {
            'subtotal': round(subtotal,2),
            'total_amount': round(total,2),
            'balance': round(balance,2),
        }

        if balance < Decimal('-999999999'):  # silly guard; adjust rules if needed
            self.add_error(None, "Balance unrealistic.")
        return cleaned
