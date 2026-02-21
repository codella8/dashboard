# daily_sale/models.py
from uuid import uuid4
from decimal import Decimal, ROUND_HALF_UP
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.core.validators import MinValueValidator
from accounts.models import UserProfile, Company
from containers.models import Inventory_List, Container
from .services import CalculationService

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
    paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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

    def calculate_amounts(self):
        return CalculationService.calculate_transaction_amounts(
            quantity=self.quantity,
            unit_price=self.unit_price,
            discount=self.discount,
            tax_percent=self.tax,
            advance=self.advance
        )

    def save(self, *args, **kwargs):
        if self.pk: 
            items = self.items.all()
            if items.exists():
                subtotal = Decimal('0')
                tax_amount = Decimal('0')
                discount_total = Decimal('0')
                
                for item in items:
                    subtotal += item.subtotal or Decimal('0')
                    tax_amount += item.tax_amount or Decimal('0')
                    discount_total += item.discount or Decimal('0')
                    
                self.subtotal = subtotal
                self.tax_amount = tax_amount
                self.total_amount = (subtotal - discount_total + tax_amount).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                self.balance = max(self.total_amount - self.advance, Decimal('0'))
                
                if self.balance <= Decimal("0") and self.total_amount > Decimal("0"):
                    self.payment_status = "paid"
                elif self.advance > Decimal("0"):
                    self.payment_status = "partial"
                else:
                    self.payment_status = "unpaid"
                    
            else:
                amounts = self.calculate_amounts()
                self.subtotal = amounts["subtotal"]
                self.tax_amount = amounts["tax_amount"]
                self.total_amount = amounts["total_amount"]
                self.balance = amounts["balance"]
                self.payment_status = amounts["payment_status"]
                
        else:
            amounts = self.calculate_amounts()
            self.subtotal = amounts["subtotal"]
            self.tax_amount = amounts["tax_amount"]
            self.total_amount = amounts["total_amount"]
            self.balance = amounts["balance"]
            self.payment_status = amounts["payment_status"]
            
        self.paid = self.advance
        super().save(*args, **kwargs)

    @property
    def taxable_amount(self):
        taxable = (self.subtotal - self.discount).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return max(taxable, Decimal("0"))
    
    @property
    def paid_percentage(self):
        if self.total_amount > 0:
            return ((self.advance / self.total_amount) * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return Decimal("0")


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

    def calculate_item_amounts(self):
        return CalculationService.calculate_item_amounts(
            quantity=self.quantity,
            unit_price=self.unit_price,
            discount=self.discount,
            tax_percent=self.transaction.tax
        )

    def save(self, *args, **kwargs):
        amounts = self.calculate_item_amounts()
        self.subtotal = amounts["subtotal"]
        self.tax_amount = amounts["tax_amount"]
        self.total_amount = amounts["total_amount"]
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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.transaction.save()


class DailySummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    date = models.DateField(unique=True, db_index=True)
    total_sales = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    total_purchases = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    total_profit = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    net_balance = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    transactions_count = models.PositiveIntegerField(default=0)
    items_sold = models.PositiveIntegerField(default=0)
    customers_count = models.PositiveIntegerField(default=0)
    

    gross_profit = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    total_returns = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    total_tax = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    total_discount = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    total_paid = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    avg_transaction_value = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    
    paid_transactions = models.PositiveIntegerField(default=0)
    partial_transactions = models.PositiveIntegerField(default=0)
    unpaid_transactions = models.PositiveIntegerField(default=0)
    total_outstanding = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))

    payment_method_cash = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    payment_method_card = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    payment_method_bank = models.DecimalField(max_digits=24, decimal_places=2, default=Decimal("0"))
    
    updated_at = models.DateTimeField(auto_now=True)
    is_final = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date"]
        verbose_name = "Daily Summary "
        verbose_name_plural = "Daily Summary "

    def __str__(self):
        return f"Daily Summary {self.date}"

    @property
    def collection_rate(self):
        if self.total_sales > 0:
            return (self.total_paid / self.total_sales * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return Decimal("0")

    @property
    def avg_items_per_transaction(self):
        if self.transactions_count > 0:
            return (self.items_sold / self.transactions_count).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        return Decimal("0")


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