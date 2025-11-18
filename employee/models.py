from django.db import models
from uuid import uuid4
from django.utils import timezone
from django.contrib.auth import get_user_model
from accounts.models import UserProfile

User = get_user_model()

class Employee(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    employee = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True)
    position = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    date = models.DateField(db_index=True)
    hire_date = models.DateField(null=True, blank=True)
    salary_due = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    debt_to_company = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.employee

class SalaryPayment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='salary_payments')
    date = models.DateField(db_index=True)
    salary_amount = models.DecimalField(max_digits=14, decimal_places=2)
    is_paid = models.BooleanField(default=False) 
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.employee} – {self.salary_amount} on {self.date}"

class EmployeeExpense(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='expenses')
    date = models.DateField(db_index=True)
    expense = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.employee} – {self.price} on {self.date}"