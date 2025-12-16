# daily_sale/forms.py
from django import forms
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone

from .models import DailySaleTransaction, Payment
from accounts.models import Company, UserProfile
from containers.models import Container, Inventory_List


class DailySaleTransactionForm(forms.ModelForm):
    class Meta:
        model = DailySaleTransaction
        fields = [
            "invoice_number", "date", "due_date", "transaction_type", "company", "container", "item",
            "quantity", "unit_price", "discount", "tax", "advance", "customer", "description", "note"
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "due_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "invoice_number": forms.TextInput(attrs={"class": "form-control"}),
            "transaction_type": forms.Select(attrs={"class": "form-select"}),
            "company": forms.Select(attrs={"class": "form-select"}),
            "container": forms.Select(attrs={"class": "form-select"}),
            "item": forms.Select(attrs={"class": "form-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "min": 1}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "discount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "tax": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "advance": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "customer": forms.Select(attrs={"class": "form-select"}),
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # خالی برای AJAX
        self.fields["company"].queryset = Company.objects.none()
        self.fields["customer"].queryset = UserProfile.objects.none()
        self.fields["container"].queryset = Container.objects.none()
        self.fields["item"].queryset = Inventory_List.objects.none()

        # برای POST پر شود
        if self.is_bound:
            self.fields["company"].queryset = Company.objects.all()
            self.fields["customer"].queryset = UserProfile.objects.all()
            self.fields["container"].queryset = Container.objects.all()
            self.fields["item"].queryset = Inventory_List.objects.all()

    def clean(self):
        cleaned_data = super().clean()

        quantity = cleaned_data.get('quantity') or 1
        unit_price = cleaned_data.get('unit_price') or Decimal("0")
        discount = cleaned_data.get('discount') or Decimal("0")
        advance = cleaned_data.get('advance') or Decimal("0")
        tax = cleaned_data.get('tax') or Decimal("0")  # درصد (مثلاً 5)

        quantity = Decimal(quantity)
        unit_price = Decimal(unit_price)
        discount = Decimal(discount)
        advance = Decimal(advance)
        tax = Decimal(tax)

        # 1. محاسبه سابتوتال با دقت بالا
        subtotal = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # 2. محاسبه مبلغ قابل مالیات (بعد از تخفیف)
        taxable_amount = (subtotal - discount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if taxable_amount < Decimal("0"):
            taxable_amount = Decimal("0")
        
        # 3. محاسبه مالیات روی مبلغ قابل مالیات - مثل ماشین حساب
        tax_amount = (taxable_amount * (tax / Decimal("100"))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        
        # 4. محاسبه مبلغ کل
        total_amount = (taxable_amount + tax_amount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # 5. محاسبه باقیمانده
        balance = (total_amount - advance).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # ست کردن مقادیر نهایی
        cleaned_data['subtotal'] = subtotal
        cleaned_data['tax_amount'] = tax_amount
        cleaned_data['total_amount'] = total_amount
        cleaned_data['balance'] = balance

        return cleaned_data


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "date", "method", "note"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "method": forms.TextInput(attrs={"class": "form-control"}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }