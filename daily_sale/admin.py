from django.contrib import admin
from .models import DailySaleTransaction
from django.utils.html import format_html

@admin.register(DailySaleTransaction)
class DailySaleTransactionAdmin(admin.ModelAdmin):
    list_display = ('invoice_number','date','transaction_type','customer','company','container','total_amount','balance','status')
    list_filter = ('transaction_type','status','currency','date')
    search_fields = ('invoice_number','item__product_name','customer__user__first_name','customer__user__email')
    readonly_fields = ('subtotal','total_amount','balance','created_at','updated_at')
    ordering = ('-date','-created_at')

    def save_model(self, request, obj, form, change):
        if not obj.created_by:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
