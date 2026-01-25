from django import forms
from .models import Employee, SalaryPayment

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = [
            'employee',
            'position',
            'employment_type',
            'is_active',
            'date',
            'hire_date',
            'termination_date',
            'salary_due',
            'debt_to_company',
            'note',
        ]
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'hire_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'termination_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'salary_due': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'debt_to_company': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'position': forms.TextInput(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class SalaryPaymentForm(forms.ModelForm):
    class Meta:
        model = SalaryPayment
        fields = [
            'employee', 
            'date',
            'salary_amount',
            'is_paid',
            'payment_method',
            'reference_number',
            'note',
        ]
        widgets = {
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'salary_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'is_paid': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
