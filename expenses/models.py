from django.db import models

class ExpenseItem(models.Model):
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)  # مثل: قطعه، خوراکی، خدمات
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    is_machine_related = models.BooleanField(default=False)

    def __str__(self):
        return self.name

class ExpenseRecord(models.Model):
    date = models.DateField()
    item = models.ForeignKey(ExpenseItem, on_delete=models.CASCADE)
    qty = models.PositiveIntegerField()
    total = models.DecimalField(max_digits=12, decimal_places=2)
    paid_by = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.item.name} – {self.total}"
    
class DailyExpense(models.Model):
    date = models.DateField()
    category = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.category} – {self.amount} on {self.date}"

