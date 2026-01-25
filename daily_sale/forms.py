# daily_sale/forms.py
from django import forms
from decimal import Decimal, ROUND_HALF_UP
from .models import DailySaleTransaction, Payment, DailySaleTransactionItem
from accounts.models import Company, UserProfile
from containers.models import Container, Inventory_List
from django.forms import inlineformset_factory

class DailySaleTransactionForm(forms.ModelForm):
    class Meta:
        model = DailySaleTransaction
        fields = [
            "invoice_number",
            "date",
            "due_date",
            "transaction_type",
            "company",
            "customer",
            "advance",
            "tax",
            "note",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "due_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "invoice_number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Auto-generated if empty"
            }),
            "transaction_type": forms.Select(attrs={"class": "form-select"}),
            "company": forms.Select(attrs={"class": "form-select"}),
            "customer": forms.Select(attrs={"class": "form-select"}),
            "advance": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
            }),
            "tax": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
            }),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["advance"].required = False
        self.fields["tax"].required = False

        self.fields["advance"].initial = Decimal("0.00")
        self.fields["tax"].initial = Decimal("5.00")

        # AJAX
        self.fields["company"].queryset = Company.objects.none()
        self.fields["customer"].queryset = UserProfile.objects.none()

        if self.is_bound:
            self.fields["company"].queryset = Company.objects.all()
            self.fields["customer"].queryset = UserProfile.objects.all()

    def clean(self):
        cleaned_data = super().clean()

        advance = cleaned_data.get("advance") or Decimal("0")
        tax = cleaned_data.get("tax") or Decimal("0")

        if advance < 0:
            raise forms.ValidationError("Advance cannot be negative")

        if tax < 0 or tax > 100:
            raise forms.ValidationError("Tax must be between 0 and 100")

        return cleaned_data

TransactionItemFormSet = inlineformset_factory(
    DailySaleTransaction,
    DailySaleTransactionItem,
    fields=["item", "container", "quantity", "unit_price", "discount", "tax_amount"],
    extra=1,
    can_delete=True,
    widgets={
        "item": forms.Select(attrs={"class": "form-select item-select"}),
        "container": forms.Select(attrs={"class": "form-select container-select"}),
        "quantity": forms.NumberInput(attrs={"class": "form-control quantity-input", "min": 1}),
        "unit_price": forms.NumberInput(attrs={"class": "form-control unit-price-input", "step": "0.01"}),
        "discount": forms.NumberInput(attrs={"class": "form-control discount-input", "step": "0.01"}),
        "tax_amount": forms.NumberInput(attrs={"class": "form-control tax-input", "step": "0.01"}),
    }
)


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