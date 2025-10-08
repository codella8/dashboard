from django.contrib import admin
from .models import Customer

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'company', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'phone', 'company', 'national_id']
    ordering = ['name']
 