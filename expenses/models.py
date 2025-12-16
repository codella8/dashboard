from django.db import models
from django.core.validators import MinValueValidator

class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="category name")
    description = models.TextField(blank=True, verbose_name="description")
    
    def __str__(self):
        return self.name
    

class ExpenseItem(models.Model):
    name = models.CharField(max_length=100, verbose_name="Item name")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, verbose_name="category")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="price")
    
    def __str__(self):
        return f"{self.name} - {self.category.name}"
    

class ExpenseRecord(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'cash'),
        ('bank', 'حواله بانکی'),
        ('card', 'کارتخوان'),
    ]
    
    date = models.DateField(verbose_name="تاریخ")
    item = models.ForeignKey(ExpenseItem, on_delete=models.CASCADE, verbose_name="آیتم")
    quantity = models.PositiveIntegerField(default=1, verbose_name="تعداد")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="قیمت واحد")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="مبلغ کل")
    paid_by = models.CharField(max_length=100, verbose_name="پرداخت کننده")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default='cash', verbose_name="روش پرداخت")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    
    def __str__(self):
        return f"{self.item.name} - {self.total_amount}"
    
    class Meta:
        verbose_name = "سابقه هزینه"
        verbose_name_plural = "سوابق هزینه‌ها"
        ordering = ['-date']

class DailyExpense(models.Model):
    date = models.DateField(verbose_name="تاریخ")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, verbose_name="دسته‌بندی")
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="مبلغ")
    description = models.TextField(blank=True, verbose_name="توضیحات")
    paid_to = models.CharField(max_length=200, blank=True, verbose_name="پرداخت به")
    
    def __str__(self):
        return f"{self.category.name} - {self.amount}"
    
    class Meta:
        verbose_name = "هزینه روزانه"
        verbose_name_plural = "هزینه‌های روزانه"
        ordering = ['-date']