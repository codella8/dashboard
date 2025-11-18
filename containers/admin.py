from django.contrib import admin
from .models import Saraf, Container, SarafTransaction, ContainerTransaction, Inventory_List

@admin.register(Inventory_List)
class InventoryListAdmin(admin.ModelAdmin):
    list_display = ('code', 'product_name', 'container', 'in_stock_qty', 'unit_price', 'price', 'total_sold_qty', 'total_sold_count')
    list_filter = ('container', 'date_added')
    search_fields = ('code', 'product_name')
    ordering = ('-date_added',)
    readonly_fields = ('date_added',)
    list_per_page = 20

    fieldsets = (
        (None, {
            'fields': ('container', 'code', 'product_name', 'make', 'model', 'in_stock_qty', 'unit_price', 'price', 'sold_price', 'total_sold_qty', 'total_sold_count', 'description')
        }),
        ('Timestamps', {
            'fields': ('date_added',),
            'classes': ('collapse',),
        }),
    )

class SarafTransactionInline(admin.TabularInline):
    model = SarafTransaction
    extra = 0
    readonly_fields = (
        "currency",
        "balance",
        "transaction_time",
        "created_at",
    )
    fields = (
        "container",
        "received_from_saraf",
        "paid_by_company",
        "debit_company",
        "balance",
        "currency",
        "transaction_time",
    )
    ordering = ("-transaction_time",)
    show_change_link = True


class ContainerTransactionInline(admin.TabularInline):
    model = ContainerTransaction
    extra = 0
    readonly_fields = ("created_at",)
    fields = (
        "product",
        "customer",
        "company",
        "sale_status",
        "payment_status",
        "transport_status",
        "total_price",
        "arrival_date",
        "arrived_date",
    )
    ordering = ("-created_at",)
    show_change_link = True


@admin.register(Saraf)
class SarafAdmin(admin.ModelAdmin):
    list_display = ("user", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("user__first_name", "user__last_name", "user__email")
    inlines = [SarafTransactionInline]
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("All Saraf information", {
            "fields": ("user", "is_active", "note"),
        }),
        ("create and update time", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def get_queryset(self, request):
        """برای بهینه‌سازی Query"""
        return super().get_queryset(request).select_related("user")

@admin.register(Container)
class ContainerAdmin(admin.ModelAdmin):
    list_display = (
        "container_number",
        "name",
        "container_product",
        "company",
        "price",
        "created_at",
    )
    list_filter = ("company", "created_at")
    search_fields = ("container_number", "name", "company__name")
    readonly_fields = ("created_at",)
    inlines = [ContainerTransactionInline]

    fieldsets = (
        ("اطلاعات کلی کانتینر", {
            "fields": (
                "container_number",
                "name",
                "container_product",
                "price",
                "company",
                "description",
            ),
        }),
        ("زمان ایجاد", {
            "fields": ("created_at",),
        }),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("company")

@admin.register(SarafTransaction)
class SarafTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "saraf",
        "currency",
        "received_from_saraf",
        "paid_by_company",
        "debit_company",
        "balance",
        "transaction_time",
    )
    list_filter = ("currency", "transaction_time")
    search_fields = ("saraf__user__first_name", "saraf__user__last_name", "container__name")
    readonly_fields = ("balance", "created_at", "updated_at")
    ordering = ("-transaction_time",)
    date_hierarchy = "transaction_time"

    fieldsets = (
        ("اطلاعات تراکنش صراف", {
            "fields": (
                "saraf",
                "container",
                "received_from_saraf",
                "paid_by_company",
    
                "debit_company",
                "balance",
                "currency",
                "description",
                "transaction_time",
            ),
        }),
        ("جزئیات فنی", {
            "classes": ("collapse",),
            "fields": ( "created_at", "updated_at"),
        }),
    )
    
@admin.register(ContainerTransaction)
class ContainerTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "container",
        "product",
        "company",
        "sale_status",
        "payment_status",
        "transport_status",
        "total_price",
        "arrival_date",
    )
    list_filter = (
        "sale_status",
        "payment_status",
        "transport_status",
        "arrival_date",
        "arrived_date",
    )
    search_fields = ("container__name", "company__name", "saraf__user__first_name")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
    date_hierarchy = "arrival_date"

    fieldsets = (
        ("جزئیات اصلی کانتینر", {
            "fields": (
                "container",
                "product",
                "company",
                "customer",
                "total_price",
                "sale_status",
                "payment_status",
                "transport_status",
            ),
        }),
        ("اطلاعات حمل و نقل", {
            "classes": ("collapse",),
            "fields": ("port_of_origin", "port_of_discharge", "arrival_date", "arrived_date", "note"),
        }),
        ("تاریخ ایجاد", {
            "fields": ("created_at",),
        }),
    )
