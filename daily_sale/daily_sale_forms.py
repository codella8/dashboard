# daily_sale/forms.py
from decimal import Decimal
from django import forms
from django.utils import timezone
from .models import DailySaleTransaction
from django.core.exceptions import ValidationError

class DailySaleTransactionForm(forms.ModelForm):
    class Meta:
        model = DailySaleTransaction
        fields = [
            "item", "invoice_number", "date", "day", "container", "customer", "company", "saraf",
            "transaction_type", "quantity", "unit_price", "advance", "paid", "discount", "tax",
            "total_amount", "balance", "description", "currency", "status", "note", "created_by"
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.TextInput(),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_quantity(self):
        q = self.cleaned_data.get("quantity") or 0
        if q < 0:
            raise ValidationError("Quantity must be non-negative.")
        return q

    def clean_unit_price(self):
        p = self.cleaned_data.get("unit_price") or Decimal("0.00")
        if p < 0:
            raise ValidationError("Unit price must be non-negative.")
        return p

    def clean(self):
        cleaned = super().clean()
        qty = cleaned.get("quantity") or 0
        unit_price = cleaned.get("unit_price") or Decimal("0.00")
        discount = cleaned.get("discount") or Decimal("0.00")
        tax = cleaned.get("tax") or Decimal("0.00")
        advance = cleaned.get("advance") or Decimal("0.00")
        paid = cleaned.get("paid") or Decimal("0.00")

        # پایه محاسبه: quantity * unit_price
        subtotal = (Decimal(qty) * unit_price).quantize(Decimal("0.01"))
        # اعمال تخفیف (فرض ما: discount به‌عنوان مبلغ است نه درصد)
        after_discount = subtotal - discount
        if after_discount < 0:
            after_discount = Decimal("0.00")
        # افزودن مالیات (مقداری ثابت)
        total_amount = (after_discount + tax).quantize(Decimal("0.01"))

        # balance = total_amount - (advance + paid)
        balance = (total_amount - (advance + paid)).quantize(Decimal("0.01"))
        if balance < 0:
            # اجازه بدهیم balance منفی باشد (بدهی معکوس) یا بخواهی آن را به صفر برسانیم
            # اینجا هیچ اروری اضافه نمی‌کنیم، اما می‌توانیم هشدار دهیم
            pass

        # مقدارها را در cleaned_data ذخیره کن تا در save هم باشند
        cleaned["total_amount"] = total_amount
        cleaned["balance"] = balance
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        # اگر فرم clean مقدارها را محاسبه کرده، آن‌ها را روی instance بنویس
        cleaned = getattr(self, "cleaned_data", {})
        if "total_amount" in cleaned:
            instance.total_amount = cleaned["total_amount"]
        if "balance" in cleaned:
            instance.balance = cleaned["balance"]
        if commit:
            instance.save()
        return instance
    