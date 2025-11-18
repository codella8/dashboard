from django.contrib import admin
from .models import Employee, SalaryPayment, EmployeeExpense
from django.utils import timezone


# -----------------------------
# Employee Admin
# ----------------------------- 
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee', 'position', 'is_active', 'hire_date', 'salary_due', 'debt_to_company', 'created_at')
    list_filter = ('is_active', 'hire_date')
    search_fields = ('employee__user__username', 'position')
    ordering = ('-hire_date',)
    readonly_fields = ('created_at',)
    list_per_page = 20

    fieldsets = (
        (None, {
            'fields': ('employee', 'position', 'is_active', 'hire_date', 'salary_due', 'debt_to_company', 'note')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )


# -----------------------------
# SalaryPayment Admin
# -----------------------------
@admin.register(SalaryPayment)
class SalaryPaymentAdmin(admin.ModelAdmin):
    list_display = ('employee', 'salary_amount', 'date', 'is_paid', 'created_at')
    list_filter = ('is_paid', 'date')
    search_fields = ('employee__employee__user__username',)
    ordering = ('-date',)
    readonly_fields = ('date',)
    list_per_page = 20

    fieldsets = (
        (None, {
            'fields': ('employee', 'salary_amount', 'is_paid', 'note')
        }),
        ('Timestamps', {
            'fields': ('date', 'created_at'),
            'classes': ('collapse',),
        }),
    )


# -----------------------------
# EmployeeExpense Admin
# -----------------------------
@admin.register(EmployeeExpense)
class EmployeeExpenseAdmin(admin.ModelAdmin):
    list_display = ('employee', 'expense', 'price', 'date', 'created_at')
    list_filter = ('date',)
    search_fields = ('employee__employee__user__username', 'expense')
    ordering = ('-date',)
    readonly_fields = ('created_at',)
    list_per_page = 20

    fieldsets = (
        (None, {
            'fields': ('employee', 'expense', 'price', 'note')
        }),
        ('Timestamps', {
            'fields': ('date', 'created_at'),
            'classes': ('collapse',),
        }),
    )
