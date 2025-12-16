# daily_sale/admin.py
from django.contrib import admin
from .models import DailySaleTransaction, Payment, DailySummary, OutstandingCustomer

@admin.register(DailySaleTransaction)
class DailySaleTransactionAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "date", "transaction_type", "customer", "company", "container", "display_total", "display_balance")
    list_filter = ("transaction_type", "date")
    search_fields = ("invoice_number", "item__product_name", "customer__user__first_name", "customer__user__email")
    readonly_fields = ("subtotal", "total_amount", "balance", "created_at", "updated_at")
    ordering = ("-date", "-created_at")

    def display_total(self, obj):
        return "" if obj.total_amount == 0 else obj.total_amount
    display_total.short_description = "Total"

    def display_balance(self, obj):
        return "" if obj.balance == 0 else obj.balance
    display_balance.short_description = "Balance"

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("transaction", "amount", "date", "created_by", "created_at")
    readonly_fields = ("created_at",)

@admin.register(DailySummary)
class DailySummaryAdmin(admin.ModelAdmin):
    list_display = ("date", "display_total_sales", "display_total_purchases", "transactions_count", "items_sold", "is_final", "updated_at")
    readonly_fields = [f.name for f in DailySummary._meta.fields]
    ordering = ("-date",)

    def display_total_sales(self, obj):
        return "" if obj.total_sales == 0 else obj.total_sales
    display_total_sales.short_description = "Total Sales"

    def display_total_purchases(self, obj):
        return "" if obj.total_purchases == 0 else obj.total_purchases
    display_total_purchases.short_description = "Total Purchases"

@admin.register(OutstandingCustomer)
class OutstandingCustomerAdmin(admin.ModelAdmin):
    list_display = ("customer", "total_debt", "transactions_count", "last_transaction", "updated_at")
    readonly_fields = [f.name for f in OutstandingCustomer._meta.fields]
    search_fields = ("customer__user__first_name", "customer__user__email")
