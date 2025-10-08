from django.contrib import admin
from .models import SaleInvoice, DailyExpense, OldTransaction, DailySaleRecord

@admin.register(SaleInvoice)
class SaleInvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_no', 'date', 'customer_name', 'total', 'balance', 'cleared']
    list_filter = ['date', 'cleared']
    search_fields = ['invoice_no', 'customer_name', 'container_no']

@admin.register(DailyExpense)
class DailyExpenseAdmin(admin.ModelAdmin):
    list_display = ['date', 'category', 'amount']
    list_filter = ['date', 'category']
    search_fields = ['category', 'description']

@admin.register(OldTransaction)
class OldTransactionAdmin(admin.ModelAdmin):
    list_display = ['invoice_no', 'due_amount', 'paid', 'discount', 'total']
    search_fields = ['invoice_no', 'description']

@admin.register(DailySaleRecord)
class DailySaleRecordAdmin(admin.ModelAdmin):
    list_display = ['date', 'total_sales', 'total_cash_in', 'total_expense', 'net_amount']
    list_filter = ['date']
