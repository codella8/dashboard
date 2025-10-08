from django.contrib import admin
from .models import DailyExpense

@admin.register(DailyExpense)
class DailyExpenseAdmin(admin.ModelAdmin):
    list_display = ['date', 'category', 'amount']
    list_filter = ['date', 'category']
    search_fields = ['category', 'description']
