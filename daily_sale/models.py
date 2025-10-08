from django.db import models

class SaleInvoice(models.Model):
    invoice_no = models.CharField(max_length=20, unique=True)
    date = models.DateField()
    customer_name = models.CharField(max_length=100)
    container_no = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    
    qty = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    
    advance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    total = models.DecimalField(max_digits=12, decimal_places=2)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    cleared = models.BooleanField(default=False)

    def __str__(self):
        return f"Invoice {self.invoice_no} – {self.customer_name}"


class DailyExpense(models.Model):
    date = models.DateField()
    category = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.category} – {self.amount} on {self.date}"

class OldTransaction(models.Model):
    invoice_no = models.CharField(max_length=20)
    description = models.TextField(blank=True, null=True)
    
    due_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"OldTransaction {self.invoice_no}"

class DailySaleRecord(models.Model):
    date = models.DateField(unique=True)
    total_sales = models.DecimalField(max_digits=12, decimal_places=2)
    total_cash_in = models.DecimalField(max_digits=12, decimal_places=2)
    total_expense = models.DecimalField(max_digits=12, decimal_places=2)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"Record for {self.date}"
