from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Expense Category"
        verbose_name_plural = "Expense Categories"

    def __str__(self):
        return self.name


class Expense(models.Model):
    PAYMENT_METHODS = [
        ("cash", "Cash"),
        ("bank", "Bank Transfer"),
        ("card", "POS / Card"),
    ]

    date = models.DateField()
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses"
    )

    title = models.CharField(max_length=200)
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(Decimal("0.01"))]
    )
    unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS,
        default="cash"
    )

    paid_to = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["category"]),
        ]
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"

    @property
    def total_amount(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.title} - {self.total_amount}"
