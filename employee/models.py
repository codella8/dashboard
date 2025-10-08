from django.db import models

class Employee(models.Model):
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    position = models.CharField(max_length=50, blank=True)
    national_id = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    hire_date = models.DateField(null=True, blank=True)
    salary_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # حقوق باقی‌مانده
    debt_to_company = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # قرض یا بدهی
    note = models.TextField(blank=True)

    def __str__(self):
        return self.full_name

class SalaryPayment(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_paid = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"{self.employee.full_name} – {self.amount} on {self.date}"

class EmployeeExpense(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    title = models.CharField(max_length=100)  # مثل غذا، حمل‌ونقل، پاداش
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    is_company_paid = models.BooleanField(default=True)  # آیا شرکت پرداخت کرده یا کارمند بدهکار شده
    note = models.TextField(blank=True)

    def __str__(self):
        return f"{self.title} – {self.amount} for {self.employee.full_name}"

