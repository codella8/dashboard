# daily_sale/models.py
from uuid import uuid4
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.core.validators import MinValueValidator

# روابط به اپ‌های دیگر — مسیرها را در صورت نیاز تنظیم کن
from accounts.models import UserProfile, Company
from containers.models import Inventory_List, Container


class DailySaleTransaction(models.Model):
    """Single sale/purchase transaction — core."""
    TRANSACTION_TYPES = [
        ("sale", "Sale"),
        ("purchase", "Purchase"),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    CURRENCY_CHOICES = [
        ('usd', 'USD'),
        ('eur', 'EUR'),
        ('aed', 'AED'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    invoice_number = models.CharField(max_length=64, unique=True, blank=True, db_index=True)
    date = models.DateField(default=timezone.now, db_index=True)
    transaction_type = models.CharField(max_length=16, choices=TRANSACTION_TYPES, default='sale')

    # related_name های اختصاصی تا با مدل‌های دیگر clash نکنند
    item = models.ForeignKey(
        Inventory_List,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='daily_transactions_for_item'
    )
    container = models.ForeignKey(
        Container,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='daily_transactions_for_container'
    )
    customer = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='daily_transactions_for_customer'
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='daily_transactions_for_company'
    )

    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    discount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    tax = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    advance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))

    subtotal = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))
    balance = models.DecimalField(max_digits=20, decimal_places=2, default=Decimal('0.00'))

    currency = models.CharField(max_length=8, choices=CURRENCY_CHOICES, default='usd')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    description = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Daily Sale Transaction"
        verbose_name_plural = "Daily Sale Transactions"
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['status']),
            models.Index(fields=['transaction_type']),
            models.Index(fields=['customer']),
        ]

    def __str__(self):
        return f"{self.invoice_number or 'INV'} - {self.transaction_type} - {self.total_amount}"

    def recalc_financials(self):
        qty = Decimal(self.quantity or 0)
        unit = Decimal(self.unit_price or Decimal('0.00'))
        discount = Decimal(self.discount or Decimal('0.00'))
        tax = Decimal(self.tax or Decimal('0.00'))
        advance = Decimal(self.advance or Decimal('0.00'))

        subtotal = qty * unit
        total = subtotal - discount + tax
        balance = total - advance

        return {
            'subtotal': subtotal.quantize(Decimal('0.01')),
            'total_amount': total.quantize(Decimal('0.01')),
            'balance': balance.quantize(Decimal('0.01')),
        }

    def save(self, *args, **kwargs):
        # compute financials before save
        fin = self.recalc_financials()
        self.subtotal = fin['subtotal']
        self.total_amount = fin['total_amount']
        self.balance = fin['balance']

        # generate invoice number if missing: INV-YYYYMMDD-0001
        if not self.invoice_number:
            date_str = (self.date or timezone.now().date()).strftime('%Y%m%d')
            prefix = f"INV-{date_str}"
            last = DailySaleTransaction.objects.filter(invoice_number__startswith=prefix).order_by('-invoice_number').first()
            if last and last.invoice_number:
                try:
                    last_num = int(last.invoice_number.split('-')[-1])
                    new_num = last_num + 1
                except Exception:
                    new_num = 1
            else:
                new_num = 1
            self.invoice_number = f"{prefix}-{new_num:04d}"

        super().save(*args, **kwargs)
