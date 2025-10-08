from django.contrib import admin
from .models import Employee, SalaryPayment, EmployeeExpense

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'position', 'phone', 'salary_due', 'debt_to_company', 'is_active', 'hire_date']
    list_filter = ['is_active', 'position']
    search_fields = ['full_name', 'phone', 'national_id', 'note']
    ordering = ['full_name']
    date_hierarchy = 'hire_date'
    readonly_fields = ['salary_due', 'debt_to_company']


@admin.register(SalaryPayment)
class SalaryPaymentAdmin(admin.ModelAdmin):
    list_display = ['employee', 'date', 'amount', 'is_paid']
    list_filter = ['is_paid', 'date']
    search_fields = ['employee__full_name', 'note']
    date_hierarchy = 'date'
    ordering = ['-date']


@admin.register(EmployeeExpense)
class EmployeeExpenseAdmin(admin.ModelAdmin):
    list_display = ['employee', 'date', 'title', 'amount', 'is_company_paid']
    list_filter = ['is_company_paid', 'date', 'title']
    search_fields = ['employee__full_name', 'title', 'note']
    date_hierarchy = 'date'
    ordering = ['-date']

