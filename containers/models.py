from uuid import uuid4
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from accounts.models import Company, UserProfile

class Saraf(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(
        UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="sarafs"
    )
    is_active = models.BooleanField(default=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Saraf" 
        verbose_name_plural = "Sarafs"
        ordering = ["-created_at"] 

    def __str__(self):
        return str(self.user) if self.user else "Unnamed Saraf"

class Container(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    container_number = models.CharField(max_length=64, unique=True, db_index=True)
    container_product = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=150, blank=True)
    price = models.DecimalField(max_digits=15, decimal_places=0, default=0)
    
    # اصلاح related_name
    company = models.ForeignKey(
        Company, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="company"  # ✅ تغییر به containers
    )
    
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Container"
        verbose_name_plural = "Containers"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.container_number} - {self.name}"
    
CURRENCY_CHOICES = [
    ("usd", "USD"),
    ("eur", "EUR"),
    ("aed", "AED"),
]

class Inventory_List(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    
    # اصلاح related_name
    container = models.ForeignKey(
        Container, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='inventory_items'  # ✅ تغییر به inventory_items
    )
    
    date_added = models.DateField(default=timezone.now, db_index=True)
    code = models.CharField(max_length=64, blank=True, db_index=True)
    product_name = models.CharField(max_length=255)
    make = models.CharField(max_length=120, blank=True)
    model = models.CharField(max_length=120, blank=True)
    in_stock_qty = models.DecimalField(max_digits=18, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    price = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    sold_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total_sold_qty = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    total_sold_count = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Inventory Item"  # ✅ بهتره اسمش رو عوض کنیم
        verbose_name_plural = "Inventory Items"
        indexes = [
            models.Index(fields=['code']), 
            models.Index(fields=['product_name'])
        ]

    def __str__(self):
        return f"{self.code} – {self.product_name}" if self.code else self.product_name



class SarafTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    saraf = models.ForeignKey(
        'Saraf', on_delete=models.CASCADE, related_name="transactions"
    )
    container = models.ForeignKey(
        'Container', on_delete=models.SET_NULL, null=True, blank=True, related_name="Saraf_transactions"
    )

    received_from_saraf = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    paid_by_company = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    debit_company = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))

    balance = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=10, choices=[
        ("usd", "USD"), ("eur", "EUR"), ("aed", "AED"),
    ], default="usd", db_index=True)

    description = models.TextField(blank=True)
    transaction_time = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Saraf Transaction"
        verbose_name_plural = "Saraf Transactions"
        ordering = ["-transaction_time", "-created_at"]
        indexes = [
            models.Index(fields=["saraf", "transaction_time"]),
            models.Index(fields=["saraf", "currency"]),
        ]

    def __str__(self):
        return f"{self.saraf} | {self.currency} | {self.transaction_time.date()}"

    def save(self, *args, **kwargs):
        """
        Compute balance automatically:
        balance = previous_balance + (received_from_saraf + debit_company) - paid_by_company
        previous sums exclude this instance (handle create/update safely).
        """
        from django.db.models import Sum

        # Aggregates of previous transactions for this saraf excluding self (if already exists)
        qs = SarafTransaction.objects.filter(saraf=self.saraf)
        if self.pk:
            qs = qs.exclude(pk=self.pk)

        agg = qs.aggregate(
            prev_received=Sum("received_from_saraf"),
            prev_paid=Sum("paid_by_company"),
            prev_debit=Sum("debit_company")
        )

        prev_received = agg.get("prev_received") or Decimal("0.00")
        prev_paid = agg.get("prev_paid") or Decimal("0.00")
        prev_debit = agg.get("prev_debit") or Decimal("0.00")

        prev_balance = (prev_received + prev_debit) - prev_paid

        # current balance = prev_balance + (this_received + this_debit) - this_paid
        self.balance = prev_balance + (self.received_from_saraf + self.debit_company) - self.paid_by_company

        super().save(*args, **kwargs)
        
class ContainerTransaction(models.Model):
    SALE_STATUS = [
        ("in_store", "In Store"),
        ("sold_to_company", "Sold to Company"),
        ("sold_to_customer", "Sold to Customer"),
    ]

    TRANSPORT_STATUS = [
        ("pending", "Pending"),
        ("in_transit", "In Transit"),
        ("in_stock", "In Stock"),
    ]

    PAYMENT_STATUS = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("partial", "Partial"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    container = models.ForeignKey(
        Container, on_delete=models.CASCADE, related_name="transactions"
    )
    customer = models.ForeignKey(
        UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchases"
    )
    company = models.ForeignKey(
        Company, on_delete=models.SET_NULL, null=True, blank=True, related_name="container_transactions"
    )

    product = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(
    max_digits=18,
    decimal_places=3,
    default=Decimal("0.000"),
    validators=[MinValueValidator(Decimal("0.000"))],
    help_text="Quantity of product involved in this transaction"
)
    port_of_origin = models.CharField(max_length=255, blank=True)
    port_of_discharge = models.CharField(max_length=255, blank=True)
    total_price = models.DecimalField(max_digits=14, decimal_places=0, validators=[MinValueValidator(0)], null=True, blank=True)

    sale_status = models.CharField(max_length=32, choices=SALE_STATUS, default="in_store")
    transport_status = models.CharField(max_length=32, choices=TRANSPORT_STATUS, default="pending")
    payment_status = models.CharField(max_length=32, choices=PAYMENT_STATUS, default="pending")

    arrival_date = models.DateField(null=True, blank=True)
    arrived_date = models.DateField(null=True, blank=True)

    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Container Transaction"
        verbose_name_plural = "Container Transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["transport_status"]),
            models.Index(fields=["arrival_date"]),
            models.Index(fields=["arrived_date"]),
        ]

    
    def __str__(self):
        return f"{self.container.container_number} | {self.product} | {self.sale_status}"

    def save(self, *args, **kwargs):
        # فقط وقتی که وضعیت فروش تغییر می‌کند
        if self.sale_status in ["sold_to_company", "sold_to_customer"]:
            try:
                inventory_item = Inventory_List.objects.filter(container=self.container).first()
                if inventory_item and inventory_item.in_stock_qty >= self.quantity:
                    inventory_item.in_stock_qty -= self.quantity
                    if self.quantity > 0:
                        inventory_item.sold_price = self.total_price / self.quantity
                    inventory_item.total_sold_qty += self.quantity
                    inventory_item.total_sold_count += 1
                    inventory_item.save()
            except Inventory_List.DoesNotExist:
                # اگر آیتم موجودی وجود نداشت، کاری نکن
                pass

        super().save(*args, **kwargs)