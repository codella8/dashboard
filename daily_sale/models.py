# daily_sale/models.py
from uuid import uuid4
from decimal import Decimal, InvalidOperation
from django.db import models, transaction
from django.utils import timezone
from django.conf import settings
# Import از اپ‌های دیگر برای ارتباط
from accounts.models import UserProfile, Company
from containers.models import Inventory_List
from containers.models import Container

DEC_ZERO = Decimal('0.00')


class DailySaleTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    item = models.ForeignKey(Inventory_List, on_delete=models.SET_NULL, null=True, blank=True)
    invoice_number = models.CharField(max_length=50, unique=True, db_index=True)
    date = models.DateField(default=timezone.now, db_index=True)
    day = models.CharField(max_length=20, null=True, blank=True)
    container = models.ForeignKey(Container, on_delete=models.SET_NULL, null=True, blank=True)
    customer = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)

    # نوع تراکنش
    TRANSACTION_TYPE = [
        ("sale", "Sale"),
        ("purchase", "Purchase"),
        ("return", "Return"),
    ]
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE, default="sale")

    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2, default=DEC_ZERO)
    advance = models.DecimalField(max_digits=15, decimal_places=2, default=DEC_ZERO)
    discount = models.DecimalField(max_digits=15, decimal_places=2, default=DEC_ZERO)
    tax = models.DecimalField(max_digits=15, decimal_places=2, default=DEC_ZERO)

    # اینها می‌توانند به‌صورت خودکار محاسبه شوند اگر کاربر مقدار ندهد
    total_amount = models.DecimalField(max_digits=15, decimal_places=2, default=DEC_ZERO)

    description = models.CharField(max_length=255, blank=True)
    currency = models.CharField(max_length=10, choices=[('usd', 'USD'), ('eur', 'EUR'), ('aed', 'AED')], default='usd')

    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ], default='pending')

    note = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['customer']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.invoice_number} - {self.get_transaction_type_display()} ({self.total_amount} {self.currency})"

    # محاسبات کمکی — قابل استفاده در template/serializers
    @property
    def subtotal(self):
        """quantity * unit_price"""
        try:
            return (Decimal(self.quantity) * (self.unit_price or DEC_ZERO)).quantize(DEC_ZERO)
        except (InvalidOperation, TypeError):
            return DEC_ZERO

    @property
    def computed_total(self):
        """subtotal - discount + tax"""
        try:
            s = self.subtotal
            after_discount = s - (self.discount or DEC_ZERO)
            if after_discount < DEC_ZERO:
                after_discount = DEC_ZERO
            return (after_discount + (self.tax or DEC_ZERO)).quantize(DEC_ZERO)
        except Exception:
            return DEC_ZERO

    @property
    def computed_balance(self):
        """total_amount - (advance + paid)"""
        try:
            total = self.total_amount or self.computed_total
            return (total - ((self.advance or DEC_ZERO) + (self.paid or DEC_ZERO))).quantize(DEC_ZERO)
        except Exception:
            return DEC_ZERO

    def save(self, *args, **kwargs):
        """
        Override save to compute total_amount and balance automatically when they are zero/blank.
        - honors explicit non-zero values provided by user
        - always keeps decimal precision consistent
        """
        # Ensure numeric fields not None
        for field in ('unit_price', 'advance', 'paid', 'discount', 'tax'):
            val = getattr(self, field)
            if val is None:
                setattr(self, field, DEC_ZERO)

        # compute total_amount if it's zero or None
        try:
            if not self.total_amount or self.total_amount == DEC_ZERO:
                self.total_amount = self.computed_total
        except Exception:
            self.total_amount = self.total_amount or DEC_ZERO

        # compute balance similarly
        try:
            if not self.balance or self.balance == DEC_ZERO:
                self.balance = self.computed_balance
        except Exception:
            self.balance = self.balance or DEC_ZERO

        # try to fill `day` from date if empty
        try:
            if not self.day and self.date:
                self.day = self.date.strftime('%A')  # english day name; you can localize as needed
        except Exception:
            pass

        # set created_by default
        # note: don't import request here — views set created_by when needed; keep a fallback
        if not self.created_by:
            try:
                # leave as null if not set by view
                pass
            except Exception:
                pass

        super().save(*args, **kwargs)


class Old_Transaction(models.Model):
    date = models.DateField(default=timezone.now, db_index=True)
    day = models.CharField(max_length=20, null=True, blank=True)
    item = models.ForeignKey(Inventory_List, on_delete=models.SET_NULL, null=True, blank=True)
    container = models.ForeignKey(Container, on_delete=models.SET_NULL, null=True, blank=True)
    customer = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True)
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)

    note = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Summary for {self.date} – {self.day}"


class DailySummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    date = models.DateField(unique=True, db_index=True)
    total_sales = models.DecimalField(max_digits=18, decimal_places=2, default=DEC_ZERO)
    total_purchase = models.DecimalField(max_digits=18, decimal_places=2, default=DEC_ZERO)
    total_expense = models.DecimalField(max_digits=18, decimal_places=2, default=DEC_ZERO)
    total_profit = models.DecimalField(max_digits=18, decimal_places=2, default=DEC_ZERO)
    net_balance = models.DecimalField(max_digits=18, decimal_places=2, default=DEC_ZERO)

    note = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return f"Summary for {self.date} – {self.net_balance}"
