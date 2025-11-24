# containers/admin.py
from django.contrib import admin
from .models import Saraf, SarafTransaction, Container, Inventory_List, ContainerTransaction
from django.utils.html import format_html
from django.http import HttpResponse
import csv
from django.utils.translation import gettext_lazy as _

@admin.register(Container)
class ContainerAdmin(admin.ModelAdmin):
    list_display = ("container_number", "name", "company", "price", "created_at")
    search_fields = ("container_number", "name", "company__name")
    list_filter = ("company",)
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
    actions = ["export_selected_csv"]

    def export_selected_csv(self, request, queryset):
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="containers.csv"'
        writer = csv.writer(response)
        writer.writerow(['Container Number', 'Name', 'Company', 'Price', 'Created At'])
        for obj in queryset:
            writer.writerow([
                obj.container_number,
                obj.name,
                obj.company.name if obj.company else '',
                obj.price,
                obj.created_at.strftime('%Y-%m-%d %H:%M')
            ])
        return response
    export_selected_csv.short_description = "Export selected containers to CSV"

@admin.register(Inventory_List)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("product_name", "code", "container", "in_stock_qty", "unit_price", "price", "date_added")
    search_fields = ("product_name", "code", "container__container_number")
    list_filter = ("container", "date_added")
    readonly_fields = ("total_sold_qty", "total_sold_count")
    ordering = ("-date_added",)
    list_per_page = 50

    def export_selected_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=inventory.csv"
        writer = csv.writer(response)
        writer.writerow(["id","code","product_name","container","in_stock_qty","unit_price","price","date_added"])
        for obj in queryset:
            writer.writerow([str(obj.id), obj.code, obj.product_name, str(obj.container or ""), str(obj.in_stock_qty), str(obj.unit_price), str(obj.price), obj.date_added.isoformat()])
        return response
    export_selected_csv.short_description = _("Export selected inventory")

@admin.register(Saraf)
class SarafAdmin(admin.ModelAdmin):
    list_display = ("short_user", "is_active", "created_at")
    search_fields = ("user__user__username", "user__first_name", "user__last_name")
    list_filter = ("is_active",)
    readonly_fields = ("created_at","updated_at")
    actions = ["export_selected_csv"]

    def short_user(self, obj):
        return str(obj.user) if obj.user else "-"
    short_user.short_description = _("User")

@admin.register(SarafTransaction)
class SarafTransactionAdmin(admin.ModelAdmin):
    list_display = ("saraf", "currency", "received_from_saraf", "paid_by_company",  "transaction_time")
    search_fields = ("saraf__user__user__username", "saraf__user__first_name", "saraf__user__last_name")
    list_filter = ("currency",)
    readonly_fields = ("created_at","updated_at")
    date_hierarchy = "transaction_time"
    actions = ["export_selected_csv"]

    def export_selected_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=saraf_transactions.csv"
        writer = csv.writer(response)
        writer.writerow(["id","saraf","container","currency","received_from_saraf","paid_by_company""transaction_time"])
        for obj in queryset:
            writer.writerow([str(obj.id), str(obj.saraf), str(obj.container or ""), obj.currency, str(obj.received_from_saraf), str(obj.paid_by_company), str(obj.balance), obj.transaction_time.isoformat()])
        return response
    export_selected_csv.short_description = _("Export selected saraf transactions")

@admin.register(ContainerTransaction)
class ContainerTransactionAdmin(admin.ModelAdmin):
    list_display = ("container", "product", "quantity", "sale_status", "transport_status", "payment_status", "created_at")
    list_filter = ("sale_status", "transport_status", "payment_status", "arrival_date")
    search_fields = ("container__container_number", "product", "customer__user__username")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"