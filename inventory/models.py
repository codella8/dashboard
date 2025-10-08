from django.db import models

class ItemCategory(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Item(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True)  # مثل AL02 یا AM01
    category = models.ForeignKey(ItemCategory, on_delete=models.SET_NULL, null=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    sold_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    total_sold_qty = models.PositiveBigIntegerField(default=0)
    total_sold_count = models.PositiveIntegerField(default=0)
    in_stock = models.PositiveBigIntegerField(default=0)
    is_machine = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.code} – {self.name}" if self.code else self.name


class StockTransaction(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    date = models.DateField()
    qty_change = models.DecimalField(max_digits=12, decimal_places=2)
    source = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"{self.qty_change} – {self.item.name} on {self.date}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.item.in_stock += int(self.qty_change)
        self.item.save()


class ItemSaleRecord(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    date = models.DateField()
    qty = models.PositiveIntegerField()
    sold_price = models.DecimalField(max_digits=12, decimal_places=2)
    customer_name = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)

    def __str__(self):
        return f"{self.item.name} – {self.qty} pcs on {self.date}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.item.in_stock -= self.qty
        self.item.total_sold_qty += self.qty
        self.item.total_sold_count += 1
        self.item.sold_price = self.sold_price 
        self.item.save()
