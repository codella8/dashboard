# financial/admin.py
from django.contrib import admin
from .models import Account, Category, CashTransaction

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "created_at")
    search_fields = ("name", "code")
    list_filter = ("is_active",)
    ordering = ("name",)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_income")
    search_fields = ("name",)
    list_filter = ("is_income",)

@admin.register(CashTransaction)
class CashTransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "account", "direction", "amount", "currency", "category", "company", "profile", "reference")
    list_filter = ("direction", "account", "category", "currency", "date")
    search_fields = ("reference", "note", "company__name", "profile__user__username")
    date_hierarchy = "date"
    ordering = ("-date", "-created_at")
    readonly_fields = ("created_at",)
    list_per_page = 50
