from django.contrib import admin
from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        "date",
        "title",
        "category",
        "payment_method",
        "total_amount",
    )
    list_filter = ("category", "payment_method", "date")
    search_fields = ("title", "paid_to")
    readonly_fields = ("created_at",)
