from django.contrib import admin
from django.utils.html import format_html
from .models import Department, Employee, SalaryPayment, EmployeeExpense


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'employee_count', 'created_at')
    search_fields = ('name', 'description')
    list_filter = ('created_at',)
    
    def employee_count(self, obj):
        return obj.employee_set.filter(is_active=True).count()
    employee_count.short_description = 'Employees'


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'position', 'department', 'employment_type', 
                   'salary_due', 'is_active', 'hire_date')
    list_filter = ('department', 'employment_type', 'is_active', 'hire_date')
    search_fields = ('employee__user__first_name', 'employee__user__last_name', 
                    'position', 'employee__user__email')
    readonly_fields = ('created_at',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('employee', 'department', 'position', 'employment_type')
        }),
        ('Dates', {
            'fields': ('date', 'hire_date', 'termination_date')
        }),
        ('Financial Information', {
            'fields': ('salary_due', 'debt_to_company')
        }),
        ('Status', {
            'fields': ('is_active', 'note', 'created_at')
        }),
    )
    
    def full_name(self, obj):
        if obj.employee and obj.employee.user:
            return f"{obj.employee.user.get_full_name()}"
        return "No User Profile"
    full_name.short_description = 'Employee Name'


@admin.register(SalaryPayment)
class SalaryPaymentAdmin(admin.ModelAdmin):
    list_display = ('employee_name', 'date', 'salary_amount', 'is_paid', 
                   'payment_method', 'status_badge')
    list_filter = ('is_paid', 'payment_method', 'date')
    search_fields = ('employee__employee__user__first_name', 
                    'employee__employee__user__last_name',
                    'reference_number')
    date_hierarchy = 'date'
    
    def employee_name(self, obj):
        return str(obj.employee)
    employee_name.short_description = 'Employee'
    
    def status_badge(self, obj):
        if obj.is_paid:
            return format_html('<span class="badge badge-success">Paid</span>')
        return format_html('<span class="badge badge-warning">Pending</span>')
    status_badge.short_description = 'Status'


@admin.register(EmployeeExpense)
class EmployeeExpenseAdmin(admin.ModelAdmin):
    list_display = ('employee_name', 'expense', 'category', 'price', 'date')
    list_filter = ('category', 'date')
    search_fields = ('expense', 'employee__employee__user__first_name',
                    'employee__employee__user__last_name')
    date_hierarchy = 'date'
    
    def employee_name(self, obj):
        return str(obj.employee)
    employee_name.short_description = 'Employee'