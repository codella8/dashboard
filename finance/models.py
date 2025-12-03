# financial/models.py
import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.conf import settings
from accounts.models import Company, UserProfile

class Account(models.Model):
    """
    Physical/virtual cash account (Cash, Bank-XYZ, Petty cash).
    Admin will create accounts in admin panel.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, unique=True, db_index=True)
    code = models.CharField(max_length=50, blank=True, db_index=True, help_text="Optional short code")
    is_active = models.BooleanField(default=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Category(models.Model):
    """
    Category for transactions (Sales Cash, Purchase, Salary, Bank Transfer, etc.)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True, db_index=True)
    is_income = models.BooleanField(default=True, help_text="True if category is income (cash in)")
    note = models.TextField(blank=True)

    def __str__(self):
        return self.name


class CashTransaction(models.Model):
    """
    Generic cash/book transaction. direction: 'in' or 'out'.
    No heavy computed fields here — reports compute aggregates.
    """
    DIRECTION_IN = "in"
    DIRECTION_OUT = "out"
    DIRECTION_CHOICES = [
        (DIRECTION_IN, "Cash In"),
        (DIRECTION_OUT, "Cash Out"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="transactions")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions")
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)
    profile = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True,
                                help_text="Optional: related user/profile for receivable/payable")
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=10, default="usd")
    reference = models.CharField(max_length=200, blank=True, help_text="Optional document/ref number")
    note = models.TextField(blank=True)
    date = models.DateField(default=timezone.now, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["account"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self):
        sign = "+" if self.direction == self.DIRECTION_IN else "-"
        return f"{self.date} {self.account.name} {sign}{self.amount} {self.currency}"
