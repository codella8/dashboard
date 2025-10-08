from django.contrib import admin

from django.contrib import admin
from .models import ExchangeOffice, ExchangeTransaction

@admin.register(ExchangeOffice)
class ExchangeOfficeAdmin(admin.ModelAdmin):
    list_display = ['name', 'location']
    search_fields = ['name', 'location']
    ordering = ['name']

@admin.register(ExchangeTransaction)
class ExchangeTransactionAdmin(admin.ModelAdmin):
    list_display = ['date', 'direction', 'amount', 'exchange_office', 'container_no']
    list_filter = ['date', 'direction', 'exchange_office']
    search_fields = ['container_no', 'exchange_office__name']
    date_hierarchy = 'date'
    ordering = ['-date']

