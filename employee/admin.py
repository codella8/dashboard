from django.contrib import admin
from .models import Employee, SalaryPayment, EmployeeExpense
from django.utils import timezone


# -----------------------------------------------------
# EMPLOYEE ADMIN – CLEAN & PROFESSIONAL
# -----------------------------------------------------
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        'employee', 'position', 'is_active', 'hire_date',
        'salary_due', 'debt_to_company'
    )
    list_filter = ('is_active', 'hire_date')
    search_fields = ('employee__user__username', 'position')
    ordering = ('-hire_date',)
    readonly_fields = ('created_at', 'salary_due', 'debt_to_company')
    list_per_page = 20

    fieldsets = (
        ("Employee Info", {
            'fields': ('employee', 'position', 'is_active', 'hire_date', 'note'),
        }),
        ("Calculated Fields (Auto)", {
            'fields': ('salary_due', 'debt_to_company'),
            'classes': ('collapse',),
        }),
        ("Internal", {
            'fields': ('created_at',),
            'classes': ('collapse',),
        }),
    )


# -----------------------------------------------------
# SALARY PAYMENT ADMIN – SIMPLE & FAST
# -----------------------------------------------------
@admin.register(SalaryPayment)
class SalaryPaymentAdmin(admin.ModelAdmin):
    list_display = ('employee', 'salary_amount', 'date', 'is_paid')
    list_filter = ('is_paid', 'date')
    search_fields = ('employee__employee__user__username',)
    ordering = ('-date',)
    readonly_fields = ('created_at', 'date')
    list_per_page = 20

    # تاریخ به صورت خودکار ساخته می‌شود
    def save_model(self, request, obj, form, change):
        if not obj.date:
            obj.date = timezone.now().date()
        super().save_model(request, obj, form, change)

    fieldsets = (
        ("Payment Info", {
            'fields': ('employee', 'salary_amount', 'is_paid', 'note'),
        }),
        ("Internal Auto Fields", {
            'fields': ('date', 'created_at'),
            'classes': ('collapse',),
        }),
    )


# -----------------------------------------------------
# EMPLOYEE EXPENSE ADMIN – CLEAN & REDUCED
# -----------------------------------------------------
@admin.register(EmployeeExpense)
class EmployeeExpenseAdmin(admin.ModelAdmin):
    list_display = ('employee', 'expense', 'price', 'date')
    list_filter = ('date',)
    search_fields = ('employee__employee__user__username', 'expense')
    ordering = ('-date',)
    readonly_fields = ('created_at', 'date')
    list_per_page = 20

    def save_model(self, request, obj, form, change):
        if not obj.date:
            obj.date = timezone.now().date()
        super().save_model(request, obj, form, change)

    fieldsets = (
        ("Expense Info", {
            'fields': ('employee', 'expense', 'price', 'note'),
        }),
        ("Internal Auto Fields", {
            'fields': ('date', 'created_at'),
            'classes': ('collapse',),
        }),
    )
