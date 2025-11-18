# daily_sale/forms.py
from django import forms
from .models import DailySaleTransaction

class DailySaleTransactionForm(forms.ModelForm):
    class Meta:
        model = DailySaleTransaction
        fields = [
            'item', 'invoice_number', 'date', 'day', 'container', 'customer', 'company',
            'transaction_type', 'quantity', 'unit_price', 'advance', 'discount', 'tax', 'total_amount',
             'description', 'currency', 'status', 'note'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'note': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_invoice_number(self):
        invoice_number = self.cleaned_data.get('invoice_number')
        if DailySaleTransaction.objects.filter(invoice_number=invoice_number).exists():
            raise forms.ValidationError('Invoice number must be unique.')
        return invoice_number
