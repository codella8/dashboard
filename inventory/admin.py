from django.contrib import admin
from .models import ItemCategory, Item, StockTransaction, ItemSaleRecord

@admin.register(ItemCategory)
class ItemCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']
    ordering = ['name']


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'unit_price', 'sold_price', 'in_stock', 'total_sold_qty', 'total_sold_count', 'is_machine']
    list_filter = ['category', 'is_machine']
    search_fields = ['name', 'description', 'code']
    list_editable = ['unit_price', 'in_stock']
    ordering = ['name']
    readonly_fields = ['total_sold_qty', 'total_sold_count', 'sold_price']


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ['item', 'date', 'qty_change', 'source']
    list_filter = ['date', 'source']
    search_fields = ['item__name', 'note']
    date_hierarchy = 'date'
    ordering = ['-date']


@admin.register(ItemSaleRecord)
class ItemSaleRecordAdmin(admin.ModelAdmin):
    list_display = ['item', 'date', 'qty', 'sold_price', 'customer_name']
    list_filter = ['date', 'item']
    search_fields = ['item__name', 'customer_name', 'note']
    date_hierarchy = 'date'
    ordering = ['-date']
