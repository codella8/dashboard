from django.db import models
from uuid import uuid4
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal
from accounts.models import UserProfile

User = get_user_model()
class Employee(models.Model):
    EMPLOYMENT_TYPE_CHOICES = [
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('freelance', 'Freelance'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    employee = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True)
    position = models.CharField(max_length=100, blank=True)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default='full_time')
    is_active = models.BooleanField(default=True)
    date = models.DateField(db_index=True)
    hire_date = models.DateField(null=True, blank=True)
    termination_date = models.DateField(null=True, blank=True)
    salary_due = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    debt_to_company = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        if self.employee and self.employee.user:
            return f"{self.employee.user.get_full_name()} - {self.position}"
        return f"Unknown Employee - {self.position}"

    @property
    def total_paid(self):
        return self.salary_payments.filter(is_paid=True).aggregate(total=models.Sum('salary_amount'))['total'] or Decimal('0')

    @property
    def total_expenses(self):
        return self.expenses.aggregate(total=models.Sum('price'))['total'] or Decimal('0')

    @property
    def remaining_salary(self):
        remaining = self.salary_due - self.total_paid - self.total_expenses - self.debt_to_company
        return max(remaining, Decimal('0'))

    @property
    def payment_status(self):
        if self.remaining_salary <= 0:
            return 'paid'
        elif self.remaining_salary < self.salary_due * Decimal('0.5'):
            return 'partial'
        return 'unpaid'

    class Meta:
        ordering = ['-hire_date']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['hire_date']),
        ]


class SalaryPayment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('bank_transfer', 'Bank Transfer'),
        ('check', 'Check'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_payments')
    date = models.DateField(db_index=True)
    salary_amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    is_paid = models.BooleanField(default=False)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='bank_transfer')
    reference_number = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.employee} – ${self.salary_amount} on {self.date}"

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['is_paid']),
        ]


class EmployeeExpense(models.Model):
    EXPENSE_CATEGORY_CHOICES = [
        ('travel', 'Travel'),
        ('equipment', 'Equipment'),
        ('other', 'Other'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='expenses')
    date = models.DateField(db_index=True)
    expense = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=EXPENSE_CATEGORY_CHOICES, default='other')
    price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.employee} – ${self.price} for {self.expense} on {self.date}"

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['category']),
        ]
