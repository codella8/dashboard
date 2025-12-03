from django.db import models
from uuid import uuid4
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from decimal import Decimal
from accounts.models import UserProfile

User = get_user_model()


class Department(models.Model):
    """مدل دپارتمان"""
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True, verbose_name="Department Name")
    description = models.TextField(blank=True, verbose_name="Description")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Created At")
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        ordering = ['name']


class Employee(models.Model):
    """مدل کارمند"""
    EMPLOYMENT_TYPE_CHOICES = [
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('contract', 'Contract'),
        ('freelance', 'Freelance'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    employee = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Employee Profile")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Department")
    position = models.CharField(max_length=100, blank=True, verbose_name="Position")
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default='full_time', verbose_name="Employment Type")
    is_active = models.BooleanField(default=True, verbose_name="Is Active")
    date = models.DateField(db_index=True, verbose_name="Date")
    hire_date = models.DateField(null=True, blank=True, verbose_name="Hire Date")
    termination_date = models.DateField(null=True, blank=True, verbose_name="Termination Date")
    salary_due = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="Salary Due")
    debt_to_company = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)], verbose_name="Debt to Company")
    note = models.TextField(blank=True, verbose_name="Note")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Created At")

    def __str__(self):
        if self.employee and self.employee.user:
            return f"{self.employee.user.get_full_name()} - {self.position}"
        return f"Unknown Employee - {self.position}"
    
    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        ordering = ['-hire_date']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['hire_date']),
            models.Index(fields=['department']),
        ]


class SalaryPayment(models.Model):
    """مدل پرداخت حقوق"""
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('check', 'Check'),
        ('digital', 'Digital Payment'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_payments', verbose_name="Employee")
    date = models.DateField(db_index=True, verbose_name="Payment Date")
    salary_amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="Salary Amount")
    is_paid = models.BooleanField(default=False, verbose_name="Is Paid")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='bank_transfer', verbose_name="Payment Method")
    reference_number = models.CharField(max_length=100, blank=True, verbose_name="Reference Number")
    note = models.TextField(blank=True, verbose_name="Note")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Created At")
    
    def __str__(self):
        return f"{self.employee} – ${self.salary_amount} on {self.date}"
    
    class Meta:
        verbose_name = "Salary Payment"
        verbose_name_plural = "Salary Payments"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['is_paid']),
        ]


class EmployeeExpense(models.Model):
    """مدل هزینه‌های کارمند"""
    EXPENSE_CATEGORY_CHOICES = [
        ('travel', 'Travel'),
        ('equipment', 'Equipment'),
        ('training', 'Training'),
        ('bonus', 'Bonus'),
        ('overtime', 'Overtime'),
        ('other', 'Other'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='expenses', verbose_name="Employee")
    date = models.DateField(db_index=True, verbose_name="Expense Date")
    expense = models.CharField(max_length=100, verbose_name="Expense Description")
    category = models.CharField(max_length=20, choices=EXPENSE_CATEGORY_CHOICES, default='other', verbose_name="Category")
    price = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)], verbose_name="Amount")
    note = models.TextField(blank=True, verbose_name="Note")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Created At")

    def __str__(self):
        return f"{self.employee} – ${self.price} for {self.expense} on {self.date}"
    
    class Meta:
        verbose_name = "Employee Expense"
        verbose_name_plural = "Employee Expenses"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['category']),
        ]