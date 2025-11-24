from django import forms
from .models import DailySaleTransaction

class DailySaleTransactionForm(forms.ModelForm):
    class Meta:
        model = DailySaleTransaction
        fields = [
            'invoice_number', 'date', 'transaction_type', 'status', 'currency',
            'item', 'quantity', 'unit_price', 'advance', 'discount', 'tax',
            'customer', 'company', 'container', 'description', 'note'
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'توضیحات تراکنش...'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'یادداشت‌های اضافی...'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'advance': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'tax': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        
        # اعتبارسنجی هوشمند
        quantity = cleaned_data.get('quantity')
        unit_price = cleaned_data.get('unit_price')
        
        if quantity and quantity <= 0:
            raise forms.ValidationError("تعداد باید بزرگتر از صفر باشد.")
        
        if unit_price and unit_price < 0:
            raise forms.ValidationError("قیمت واحد نمی‌تواند منفی باشد.")
        
        return cleaned_data