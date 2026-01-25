from uuid import uuid4
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.core.validators import MinValueValidator
from accounts.models import UserProfile, Company
from containers.models import Inventory_List, Container

class DailySaleTransaction(models.Model):
    TRANSACTION_TYPES = [("sale", "Sale"), ("purchase", "Purchase")]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    invoice_number = models.CharField(max_length=64, unique=True, blank=True, db_index=True)
    date = models.DateField(default=timezone.now, db_index=True)
    due_date = models.DateField(null=True, blank=True)
    transaction_type = models.CharField(max_length=16, choices=TRANSACTION_TYPES, default="sale")

    item = models.ForeignKey(Inventory_List, on_delete=models.SET_NULL, null=True, blank=True, related_name="daily_transactions")
    container = models.ForeignKey(Container, on_delete=models.SET_NULL, null=True, blank=True, related_name="daily_transactions")
    customer = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="daily_transactions")
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, related_name="daily_transactions")

    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    discount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    tax = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    advance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)  # فیلد پرداخت شده
    payment_status = models.CharField(
        max_length=20,
        choices=[('unpaid', 'Unpaid'), ('partial', 'Partial'), ('paid', 'Paid')],
        default='unpaid'
    )

    subtotal = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0"))
    balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0"))

    description = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Daily Sale Transaction"
        verbose_name_plural = "Daily Sale Transactions"
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["transaction_type"]),
            models.Index(fields=["customer"]),
        ]

    def __str__(self):
        return f"{self.invoice_number or 'INV'} | {self.date} | {self.total_amount}"

    def save(self, *args, **kwargs):
        self.subtotal = (Decimal(self.quantity) * Decimal(self.unit_price)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        taxable_amount = (self.subtotal - Decimal(self.discount)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if taxable_amount < Decimal("0"):
            taxable_amount = Decimal("0")

        tax_rate = Decimal(self.tax) / Decimal("100")
        self.tax_amount = (taxable_amount * tax_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        self.total_amount = (taxable_amount + self.tax_amount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        self.balance = (
            self.total_amount - Decimal(self.advance) - Decimal(self.paid)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if self.balance <= Decimal("0"):
            self.payment_status = "paid"
        elif Decimal(self.advance) > Decimal("0") or Decimal(self.paid) > Decimal("0"):
            self.payment_status = "partial"
        else:
            self.payment_status = "unpaid"

        super().save(*args, **kwargs)
        
    def recalculate_totals(self):
    
        if self.items.exists():
            self.subtotal = sum((i.subtotal for i in self.items.all()), Decimal("0"))
            self.tax_amount = sum((i.tax_amount for i in self.items.all()), Decimal("0"))
            self.total_amount = sum((i.total_amount for i in self.items.all()), Decimal("0"))

            self.balance = (
                self.total_amount - Decimal(self.advance) - Decimal(self.paid)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            if self.balance <= Decimal("0"):
                self.payment_status = "paid"
            elif self.advance > 0 or self.paid > 0:
                self.payment_status = "partial"
            else:
                self.payment_status = "unpaid"

            super().save(update_fields=[
                "subtotal", "tax_amount", "total_amount",
                "balance", "payment_status"
            ])
    @property
    def taxable_amount(self):
        return self.subtotal - self.total_discount
    
    @property
    def paid_percentage(self):
        if self.total_amount > 0:
            return (self.advance / self.total_amount) * 100
        return 0



class DailySaleTransactionItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)

    transaction = models.ForeignKey(
        DailySaleTransaction,
        on_delete=models.CASCADE,
        related_name="items"
    )

    item = models.ForeignKey(
        Inventory_List,
        on_delete=models.PROTECT,
        related_name="daily_sale_items"
    )

    container = models.ForeignKey(
        Container,
        on_delete=models.SET_NULL,
        null=True,
        blank=True 
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL, null=True, 
        blank=True
        )

    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    discount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    subtotal = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0"))
    tax_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0"))
    total_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0"))

    class Meta:
        unique_together = ("transaction", "item")
        ordering = ["id"]

    def save(self, *args, **kwargs):
        self.subtotal = (Decimal(self.quantity) * self.unit_price).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        taxable = (self.subtotal - self.discount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if taxable < Decimal("0"):
            taxable = Decimal("0")

        tax_rate = Decimal(self.transaction.tax) / Decimal("100")
        self.tax_amount = (taxable * tax_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        self.total_amount = (taxable + self.tax_amount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        super().save(*args, **kwargs)


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    transaction = models.ForeignKey(DailySaleTransaction, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal("0"))
    date = models.DateField(default=timezone.now)
    method = models.CharField(max_length=64, blank=True)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.transaction.invoice_number} - {self.amount}"


class DailySummary(models.Model):
    id = models.BigAutoField(primary_key=True)
    date = models.DateField(unique=True, db_index=True)
    total_sales = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    total_purchases = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    total_profit = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    net_balance = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    transactions_count = models.PositiveIntegerField(default=0)
    items_sold = models.PositiveIntegerField(default=0)
    customers_count = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    is_final = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"Daily Summary {self.date}"


class OutstandingCustomer(models.Model):
    customer = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name="outstanding")
    total_debt = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    transactions_count = models.PositiveIntegerField(default=0)
    last_transaction = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-total_debt"]

    def __str__(self):
        return f"{getattr(self.customer, 'user', self.customer)} - {self.total_debt}"


