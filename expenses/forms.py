from django import forms
from .models import Expense


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "date",
            "category",
            "title",
            "quantity",
            "unit_price",
            "payment_method",
            "paid_to",
            "description",
        ]
