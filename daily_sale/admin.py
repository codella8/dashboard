from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html
from .models import DailySaleTransaction, DailySummary
from .report import auto_update_daily_summary, get_auto_alerts

@admin.register(DailySaleTransaction)
class DailySaleTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'invoice_number',
        'transaction_type',
        'date',
        'customer',
        'item',
        'quantity',
        'total_amount',
        'balance',
        'status',
        'is_fully_paid'
    ]
    
    list_filter = ['transaction_type', 'status', 'currency', 'date']
    search_fields = ['invoice_number', 'customer__user__username', 'item__product_name']
    readonly_fields = ['subtotal', 'total_amount', 'balance', 'created_at', 'updated_at']
    actions = ['mark_as_paid', 'recalculate_financials']
    
    fieldsets = (
        ('Base Info', {
            'fields': ('invoice_number', 'date', 'transaction_type', 'status', 'currency')
        }),
        ('Prices', {
            'fields': ('item', 'quantity', 'unit_price', 'advance', 'discount', 'tax')
        }),
        ('Counted', {
            'fields': ('subtotal', 'total_amount', 'balance'),
            'classes': ('collapse',)
        }),
        ('Users', {
            'fields': ('customer', 'company', 'container'),
            'classes': ('collapse',)
        }),
        ('Discription', {
            'fields': ('description', 'note')
        })
    )

    def mark_as_paid(self, request, queryset):
        """علامت‌گذاری خودکار به عنوان پرداخت شده"""
        for transaction in queryset:
            transaction.mark_as_paid()
        self.message_user(request, f"{queryset.count()} paid transactions signed.")
    mark_as_paid.short_description = "sign paid transactions"

    def recalculate_financials(self, request, queryset):
        """بازمحاسبه خودکار مقادیر مالی"""
        for transaction in queryset:
            transaction.calculate_financials()
            transaction.save()
        self.message_user(request, f"{queryset.count()} prices counted")
    recalculate_financials.short_description = "count transactions"

@admin.register(DailySummary)
class DailySummaryAdmin(admin.ModelAdmin):
    list_display = [
        'date',
        'get_total_sales',
        'get_total_profit',
        'get_profit_margin',
        'transactions_count',
        'get_net_balance',
        'is_final',
        'updated_at'
    ]
    
    list_filter = ['date', 'is_final']
    readonly_fields = [
        'total_sales', 'total_purchases', 'total_profit', 'net_balance',
        'transactions_count', 'items_sold', 'customers_count',
        'usd_total', 'eur_total', 'aed_total', 'updated_at'
    ]
    actions = ['recalculate_totals', 'finalize_summaries']
    
    def get_total_sales(self, obj):
        return format_html('<strong>{:,.0f}</strong>', obj.total_sales)
    get_total_sales.short_description = 'Total Sales'

    def get_total_profit(self, obj):
        color = 'green' if obj.total_profit > 0 else 'red'
        return format_html('<span style="color: {};">{:,.0f}</span>', color, obj.total_profit)
    get_total_profit.short_description = 'Total Profit'

    def get_profit_margin(self, obj):
        return f"{obj.profit_margin}%"
    get_profit_margin.short_description = 'Profit'

    def get_net_balance(self, obj):
        return format_html('<strong>{:,.0f}</strong>', obj.net_balance)
    get_net_balance.short_description = 'Net Balance'

    def recalculate_totals(self, request, queryset):
        """بازمحاسبه خودکار خلاصه‌ها"""
        for summary in queryset:
            summary.calculate_totals()
            summary.save()
        self.message_user(request, f"{queryset.count()} Counted.")
    recalculate_totals.short_description = "Count Transactions"

    def finalize_summaries(self, request, queryset):
        """نهایی کردن خودکار خلاصه‌ها"""
        for summary in queryset:
            summary.finalize()
        self.message_user(request, f"{queryset.count()}Finished .")
    finalize_summaries.short_description = "finish"