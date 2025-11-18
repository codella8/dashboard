from django.contrib import admin
from .models import DailySaleTransaction, Old_Transaction, DailySummary
from django.utils import timezone

@admin.register(DailySaleTransaction)
class DailySaleTransactionAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'transaction_type', 'quantity', 'unit_price', 'total_amount', 'status', 'created_at')
    list_filter = ('transaction_type', 'status', 'currency', 'date')
    search_fields = ('invoice_number', 'container__container_number', 'customer__user__username', 'company__name')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 20

    fieldsets = (
        (None, {
            'fields': ('invoice_number', 'transaction_type', 'item', 'quantity', 'unit_price', 'advance', 'discount', 'tax', 'total_amount', 'currency', 'status', 'note', 'description')
        }),
        ('Relations', { 
            'fields': ('container', 'customer', 'company',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(Old_Transaction)
class Old_TransactionAdmin(admin.ModelAdmin):
    list_display = ('date', 'container', 'customer', 'company', 'note', 'updated_at')
    list_filter = ('date',)
    search_fields = ('container__container_number', 'customer__user__username', 'company__name')
    ordering = ('-updated_at',)
    readonly_fields = ('updated_at',)
    list_per_page = 20

    fieldsets = (
        (None, {
            'fields': ('date', 'container', 'customer', 'company', 'note')
        }),
        ('Timestamps', {
            'fields': ('updated_at',),
            'classes': ('collapse',),
        }),
    )


# -----------------------------
# DailySummary Admin
# -----------------------------
@admin.register(DailySummary)
class DailySummaryAdmin(admin.ModelAdmin):
    list_display = ('date', 'total_sales', 'total_purchase', 'total_expense', 'total_profit', 'net_balance', 'updated_at')
    list_filter = ('date',)
    search_fields = ('date',)
    ordering = ('-date',)
    readonly_fields = ('updated_at',)
    list_per_page = 20

    fieldsets = (
        (None, {
            'fields': ('date', 'total_sales', 'total_purchase', 'total_expense', 'total_profit', 'net_balance', 'note')
        }),
        ('Timestamps', {
            'fields': ('updated_at',),
            'classes': ('collapse',),
        }),
    )
