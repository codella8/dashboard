from django.contrib import admin
from .models import ExpenseCategory, ExpenseItem, ExpenseRecord, DailyExpense

@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']

@admin.register(ExpenseItem)
class ExpenseItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'unit_price']
    list_filter = ['category']
    search_fields = ['name']

@admin.register(ExpenseRecord)
class ExpenseRecordAdmin(admin.ModelAdmin):
    list_display = ['date', 'item', 'quantity', 'unit_price', 'total_amount', 'paid_by', 'payment_method']
    list_filter = ['date', 'payment_method']
    search_fields = ['item__name', 'paid_by', 'description']

@admin.register(DailyExpense)
class DailyExpenseAdmin(admin.ModelAdmin):
    list_display = ['date', 'category', 'amount', 'paid_to']
    list_filter = ['date', 'category']
    search_fields = ['category__name', 'paid_to', 'description']